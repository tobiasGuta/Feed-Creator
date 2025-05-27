from flask import Flask, render_template, request, redirect, url_for
from bs4 import BeautifulSoup
import requests
from datetime import datetime
from urllib.parse import urljoin
import sqlite3
import threading
import time

app = Flask(__name__)
DB = 'feeds.db'

# -------- DB Setup --------
def init_db():
    conn = sqlite3.connect(DB)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS feed_configs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT UNIQUE NOT NULL,
            item_selector TEXT,
            title_selector TEXT,
            desc_selector TEXT,
            url_selector TEXT,
            date_selector TEXT,
            date_format TEXT,
            image_selector TEXT,
            min_title_length INTEGER,
            min_desc_length INTEGER,
            discord_webhook TEXT,
            last_post_url TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# -------- Helpers --------
def auto_detect_selectors(soup):
    candidates = soup.find_all(['article', 'div', 'section'], recursive=True)
    for candidate in candidates:
        if candidate.find(['h1', 'h2', 'h3']) and candidate.find('p'):
            class_list = candidate.get("class", [])
            if class_list:
                return f"{candidate.name}.{'.'.join(class_list)}"
            else:
                return candidate.name
    return ''

def extract_items(soup, base_url, config):
    items = []
    item_selector = config.get('item_selector', '').strip()
    if not item_selector:
        return items

    try:
        min_title_len = int(config.get('min_title_length', 0))
    except (ValueError, TypeError):
        min_title_len = 0
    try:
        min_desc_len = int(config.get('min_desc_length', 0))
    except (ValueError, TypeError):
        min_desc_len = 0

    elements = soup.select(item_selector)
    for el in elements:
        title = (
            el.select_one(config.get('title_selector', '')).get_text(strip=True)
            if config.get('title_selector') and el.select_one(config['title_selector'])
            else ''
        )
        description = (
            el.select_one(config.get('desc_selector', '')).get_text(strip=True)
            if config.get('desc_selector') and el.select_one(config['desc_selector'])
            else ''
        )
        link = (
            urljoin(base_url, el.select_one(config.get('url_selector', ''))['href'])
            if config.get('url_selector') and el.select_one(config['url_selector']) and el.select_one(config['url_selector']).has_attr('href')
            else ''
        )
        date_str = (
            el.select_one(config.get('date_selector', '')).get_text(strip=True)
            if config.get('date_selector') and el.select_one(config['date_selector'])
            else ''
        )
        image_url = (
            urljoin(base_url, el.select_one(config.get('image_selector', ''))['src'])
            if config.get('image_selector') and el.select_one(config['image_selector']) and el.select_one(config['image_selector']).has_attr('src')
            else ''
        )

        try:
            date = datetime.strptime(date_str, config.get('date_format')) if date_str and config.get('date_format') else None
        except Exception:
            date = None

        if len(title) >= min_title_len and len(description) >= min_desc_len:
            items.append({
                'title': title,
                'description': description,
                'url': link,
                'date': date.strftime('%Y-%m-%d') if date else '',
                'image': image_url
            })

    return items

# -------- DB Operations --------
def get_config_by_url(url):
    conn = sqlite3.connect(DB)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM feed_configs WHERE url=?", (url,))
    row = cursor.fetchone()
    conn.close()
    if row:
        keys = ['id', 'url', 'item_selector', 'title_selector', 'desc_selector', 'url_selector', 'date_selector', 'date_format', 'image_selector', 'min_title_length', 'min_desc_length', 'discord_webhook', 'last_post_url']
        return dict(zip(keys, row))
    return None

def save_config_to_db(config, url):
    conn = sqlite3.connect(DB)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO feed_configs (url, item_selector, title_selector, desc_selector, url_selector, date_selector, date_format, image_selector, min_title_length, min_desc_length, discord_webhook)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(url) DO UPDATE SET
          item_selector=excluded.item_selector,
          title_selector=excluded.title_selector,
          desc_selector=excluded.desc_selector,
          url_selector=excluded.url_selector,
          date_selector=excluded.date_selector,
          date_format=excluded.date_format,
          image_selector=excluded.image_selector,
          min_title_length=excluded.min_title_length,
          min_desc_length=excluded.min_desc_length,
          discord_webhook=excluded.discord_webhook
    """, (
        url,
        config.get('item_selector'),
        config.get('title_selector'),
        config.get('desc_selector'),
        config.get('url_selector'),
        config.get('date_selector'),
        config.get('date_format'),
        config.get('image_selector'),
        int(config.get('min_title_length', 0) or 0),
        int(config.get('min_desc_length', 0) or 0),
        config.get('discord_webhook')
    ))
    conn.commit()
    conn.close()

def update_last_post_url(url, last_post_url):
    conn = sqlite3.connect(DB)
    cursor = conn.cursor()
    cursor.execute("UPDATE feed_configs SET last_post_url=? WHERE url=?", (last_post_url, url))
    conn.commit()
    conn.close()

# -------- Discord Notification --------
def send_discord_notification(webhook_url, content):
    try:
        data = {"content": content}
        r = requests.post(webhook_url, json=data, timeout=10)
        r.raise_for_status()
    except Exception as e:
        print(f"[Discord webhook error] {e}")

# -------- Background Feed Checker --------
def check_feeds_loop(app):
    with app.app_context():
        while True:
            conn = sqlite3.connect(DB)
            cursor = conn.cursor()
            cursor.execute("SELECT url, item_selector, title_selector, desc_selector, url_selector, date_selector, date_format, image_selector, min_title_length, min_desc_length, discord_webhook, last_post_url FROM feed_configs")
            rows = cursor.fetchall()
            conn.close()

            for row in rows:
                url, item_sel, title_sel, desc_sel, url_sel, date_sel, date_fmt, img_sel, min_t, min_d, webhook, last_url = row
                if not webhook:
                    continue

                try:
                    response = requests.get(url, timeout=10)
                    response.raise_for_status()
                    soup = BeautifulSoup(response.text, 'html.parser')

                    config = {
                        'item_selector': item_sel,
                        'title_selector': title_sel,
                        'desc_selector': desc_sel,
                        'url_selector': url_sel,
                        'date_selector': date_sel,
                        'date_format': date_fmt,
                        'image_selector': img_sel,
                        'min_title_length': min_t,
                        'min_desc_length': min_d,
                    }
                    items = extract_items(soup, url, config)
                    if not items:
                        continue

                    newest_post = items[0]  # assume newest first
                    if newest_post['url'] != last_url:
                        message = f"**New post detected!**\n**Title:** {newest_post['title']}\n**Link:** {newest_post['url']}"
                        send_discord_notification(webhook, message)
                        update_last_post_url(url, newest_post['url'])

                except Exception as e:
                    print(f"[Feed check error] {url}: {e}")

            time.sleep(300)  # 5 minutes pause

# -------- Routes --------
@app.route('/', methods=['GET', 'POST'])
def index():
    error = None
    items = []
    url = ''
    config = {}
    saved = request.args.get('saved')

    # Load saved URLs for display
    with sqlite3.connect(DB) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT url FROM feed_configs ORDER BY id DESC")
        saved_configs = [row[0] for row in cursor.fetchall()]

    if request.method == 'POST':
        url = request.form.get('url', '').strip()
        action = request.form.get('action')
        advanced = request.form.get('advanced') == 'on'

        if not url:
            error = "URL is required."
            return render_template('index.html', error=error, config=request.form, url=url, saved_configs=saved_configs)

        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
        except Exception as e:
            error = f"Failed to fetch URL: {e}"
            return render_template('index.html', error=error, config=request.form, url=url, saved_configs=saved_configs)

        soup = BeautifulSoup(response.text, 'html.parser')

        if advanced:
            try:
                min_title_len = int(request.form.get('min_title_length') or 0)
                min_desc_len = int(request.form.get('min_desc_length') or 0)
            except ValueError:
                min_title_len = 0
                min_desc_len = 0

            config = {
                'item_selector': request.form.get('item_selector', '').strip(),
                'title_selector': request.form.get('title_selector', '').strip(),
                'desc_selector': request.form.get('desc_selector', '').strip(),
                'url_selector': request.form.get('url_selector', '').strip(),
                'date_selector': request.form.get('date_selector', '').strip(),
                'date_format': request.form.get('date_format', '').strip(),
                'image_selector': request.form.get('image_selector', '').strip(),
                'min_title_length': min_title_len,
                'min_desc_length': min_desc_len,
                'discord_webhook': request.form.get('discord_webhook', '').strip()
            }

            if not config['item_selector']:
                error = "Item selector is required in Advanced mode."
                return render_template('index.html', error=error, config=config, url=url, saved_configs=saved_configs)

        else:
            auto_selector = auto_detect_selectors(soup)
            saved_config = get_config_by_url(url)
            config = {
                'item_selector': auto_selector,
                'title_selector': 'h3',
                'desc_selector': 'p',
                'url_selector': 'a',
                'date_selector': 'span',
                'date_format': '',
                'image_selector': 'img',
                'min_title_length': 0,
                'min_desc_length': 0,
                'discord_webhook': saved_config['discord_webhook'] if saved_config else ''
            }

        if action == 'save':
            save_config_to_db(config, url)

            if config['discord_webhook']:
                send_discord_notification(
                    config['discord_webhook'],
                    f"✅ Feedgen: Configuration saved for `{url}`.\nYou'll get future updates here!"
                )

                existing_config = get_config_by_url(url)
                if existing_config and not existing_config.get('last_post_url'):
                    latest_url = send_initial_latest_post(url, config)
                    if latest_url:
                        update_last_post_url(url, latest_url)

            return redirect(url_for('index', url=url, saved=1))

        elif action == 'preview':
            items = extract_items(soup, url, config)

            # COMMENTED OUT to avoid notification spam on preview
            # if config.get('discord_webhook') and items:
            #     latest = items[0]  # Assuming first item is latest
            #     msg = (
            #         f"🆕 New post detected!\n"
            #         f"**{latest.get('title', 'No Title')}**\n"
            #         f"{latest.get('description', '')[:200]}...\n"
            #         f"Read more: {latest.get('url')}"
            #     )
            #     send_discord_notification(config['discord_webhook'], msg)

            return render_template('index.html', url=url, items=items, config=config, saved_configs=saved_configs)

    # GET request or after POST processing: load saved config if url param passed
    url = request.args.get('url', '').strip()
    if url:
        saved_config = get_config_by_url(url)
        if saved_config:
            config = saved_config

    return render_template('index.html', url=url, config=config or {}, items=items, error=error, saved=saved, saved_configs=saved_configs)


# -------- configuration --------
def send_initial_latest_post(url, config):
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        items = extract_items(soup, url, config)
        if items:
            latest_post = items[0]  # assuming newest first
            message = f"🚀 Initial post for `{url}`:\n**{latest_post['title']}**\n{latest_post['url']}"
            send_discord_notification(config['discord_webhook'], message)
            return latest_post['url']
    except Exception as e:
        print(f"[Initial post error] {e}")
    return None

@app.route('/configs')
def list_configs():
    conn = get_db_connection()
    configs = conn.execute('SELECT id, url FROM feed_configs').fetchall()
    conn.close()
    return render_template('configs.html', configs=configs)

def get_all_configs():
    conn = sqlite3.connect(DB)
    cursor = conn.cursor()
    cursor.execute("SELECT id, url FROM feed_configs ORDER BY id DESC")
    rows = cursor.fetchall()
    conn.close()
    return [{'id': r[0], 'url': r[1]} for r in rows]

@app.route('/configs/edit/<int:config_id>', methods=['GET', 'POST'])
def edit_config(config_id):
    conn = get_db_connection()
    config = conn.execute('SELECT * FROM configs WHERE id = ?', (config_id,)).fetchone()

    if not config:
        flash("Config not found.", "danger")
        return redirect(url_for('list_configs'))

    if request.method == 'POST':
        # grab form data same as your index()
        new_data = {
            'item_selector': request.form.get('item_selector', '').strip(),
            'title_selector': request.form.get('title_selector', '').strip(),
            'desc_selector': request.form.get('desc_selector', '').strip(),
            'url_selector': request.form.get('url_selector', '').strip(),
            'date_selector': request.form.get('date_selector', '').strip(),
            'date_format': request.form.get('date_format', '').strip(),
            'image_selector': request.form.get('image_selector', '').strip(),
            'min_title_length': request.form.get('min_title_length', '').strip(),
            'min_desc_length': request.form.get('min_desc_length', '').strip(),
            'discord_webhook': request.form.get('discord_webhook', '').strip(),
        }

        conn.execute('''
            UPDATE configs SET
                item_selector = :item_selector,
                title_selector = :title_selector,
                desc_selector = :desc_selector,
                url_selector = :url_selector,
                date_selector = :date_selector,
                date_format = :date_format,
                image_selector = :image_selector,
                min_title_length = :min_title_length,
                min_desc_length = :min_desc_length,
                discord_webhook = :discord_webhook
            WHERE id = :id
        ''', {**new_data, 'id': config_id})
        conn.commit()
        conn.close()
        flash("Configuration updated!", "success")
        return redirect(url_for('list_configs'))

    conn.close()
    return render_template('edit_config.html', config=config)

@app.route('/load_config/<int:config_id>')
def load_config(config_id):
    conn = sqlite3.connect(DB)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM feed_configs WHERE id=?", (config_id,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        return redirect(url_for('index'))

    keys = ['id', 'url', 'item_selector', 'title_selector', 'desc_selector', 'url_selector', 'date_selector', 'date_format', 'image_selector', 'min_title_length', 'min_desc_length', 'discord_webhook', 'last_post_url']
    config = dict(zip(keys, row))
    all_configs = get_all_configs()
    return render_template('index.html', url=config['url'], config=config, items=[], error=None, saved=None, all_configs=all_configs)

# -------- Start background thread --------
if __name__ == '__main__':
    threading.Thread(target=check_feeds_loop, args=(app,), daemon=True).start()
    app.run(host='0.0.0.0', port=5000, debug=True)
