import os
import sqlite3 # 雖然我們用 SQLAlchemy，但保留它可以捕捉特定的錯誤
from flask import Flask, render_template, request, redirect, url_for, g
from datetime import datetime
from zoneinfo import ZoneInfo # 【新增】引入時區資訊函式庫
from flask_sqlalchemy import SQLAlchemy
from flask_httpauth import HTTPBasicAuth
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)

# --- 資料庫設定 ---
# 增加一個 Heroku/Render 的 postgresql 協議替換，增加相容性
db_uri = os.environ.get('DATABASE_URL', 'sqlite:///novel_site.db')
if db_uri.startswith("postgres://"):
    db_uri = db_uri.replace("postgres://", "postgresql://", 1)
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///novel_site.db').replace("postgres://", "postgresql://", 1)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# --- 認證設定 ---
auth = HTTPBasicAuth()
admin_user = os.environ.get('ADMIN_USERNAME', 'admin')
admin_pass = os.environ.get('ADMIN_PASSWORD', 'password')
users = { admin_user: generate_password_hash(admin_pass) }

@auth.verify_password
def verify_password(username, password):
    if username in users and check_password_hash(users.get(username), password):
        return username

# --- 【最終版】資料模型 ---
class Book(db.Model):
    __tablename__ = 'books'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False, unique=True)
    author = db.Column(db.String(100))
    summary = db.Column(db.Text)
    created_timestamp = db.Column(db.String(20), nullable=False)
    chapters = db.relationship('Chapter', backref='book', cascade="all, delete-orphan", lazy=True)
    edit_logs = db.relationship('BookEditLog', backref='book', cascade="all, delete-orphan", lazy=True)

class Chapter(db.Model):
    __tablename__ = 'chapters'
    id = db.Column(db.Integer, primary_key=True)
    book_id = db.Column(db.Integer, db.ForeignKey('books.id'), nullable=False)
    chapter_number = db.Column(db.Integer, nullable=False)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.String(20), nullable=False)
    comments = db.relationship('Comment', backref='chapter', cascade="all, delete-orphan", lazy=True)
    edit_logs = db.relationship('ChapterEditLog', backref='chapter', cascade="all, delete-orphan", lazy=True)

class Comment(db.Model):
    __tablename__ = 'comments'
    id = db.Column(db.Integer, primary_key=True)
    chapter_id = db.Column(db.Integer, db.ForeignKey('chapters.id'), nullable=False)
    author = db.Column(db.String(100), nullable=False)
    content = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.String(20), nullable=False)
    last_edited_timestamp = db.Column(db.String(20))
    edit_logs = db.relationship('CommentEditLog', backref='comment', cascade="all, delete-orphan", lazy=True)
    
class BookEditLog(db.Model):
    __tablename__ = 'book_edit_logs'
    id = db.Column(db.Integer, primary_key=True)
    book_id = db.Column(db.Integer, db.ForeignKey('books.id'), nullable=False)
    old_title = db.Column(db.String(200), nullable=False)
    old_author = db.Column(db.String(100))
    old_summary = db.Column(db.Text)
    edit_timestamp = db.Column(db.String(20), nullable=False)

class ChapterEditLog(db.Model):
    __tablename__ = 'chapter_edit_logs'
    id = db.Column(db.Integer, primary_key=True)
    chapter_id = db.Column(db.Integer, db.ForeignKey('chapters.id'), nullable=False)
    old_title = db.Column(db.String(200), nullable=False)
    old_content = db.Column(db.Text, nullable=False)
    edit_timestamp = db.Column(db.String(20), nullable=False)

class CommentEditLog(db.Model):
    __tablename__ = 'comment_edit_logs'
    id = db.Column(db.Integer, primary_key=True)
    comment_id = db.Column(db.Integer, db.ForeignKey('comments.id'), nullable=False)
    old_content = db.Column(db.Text, nullable=False)
    edit_timestamp = db.Column(db.String(20), nullable=False)
    
# --- 【請將這整段全新的函式複製到這裡】 ---
def get_current_taipei_time():
    """
    一個輔助函式，專門用來取得當前台北(GMT+8)時間，並格式化成我們需要的字串。
    """
    # 定義我們要使用的時區
    taipei_tz = ZoneInfo("Asia/Taipei")
    # 取得帶有該時區資訊的當下時間
    taipei_now = datetime.now(taipei_tz)
    # 將時間物件格式化成字串並回傳
    return taipei_now.strftime("%Y-%m-%d %H:%M:%S")
    
# --- 【新增】建立資料庫表格的指令 ---
@app.cli.command("init-db")
def init_db_command():
    """
    清除現有資料並建立新的資料表。
    這個指令專門用於在 Render 部署時初始化資料庫。
    """
    with app.app_context():
        db.create_all()
    print("Initialized the database and created all tables.")

# --- 輔助函式 ---
def get_all_books():
    return Book.query.order_by(Book.title).all()

# --- 主要路由 ---
@app.route('/')
@auth.login_required
def index():
    books = Book.query.order_by(Book.created_timestamp.desc()).all()
    return render_template('index.html', books=books, all_books=get_all_books())

@app.route('/book/<int:book_id>')
@auth.login_required
def view_book_toc(book_id):
    book = Book.query.get_or_404(book_id)
    chapters = Chapter.query.filter_by(book_id=book_id).order_by(Chapter.chapter_number.asc()).all()
    return render_template('book_toc.html', book=book, chapters=chapters, all_books=get_all_books())

@app.route('/chapter/<int:chapter_id>')
@auth.login_required
def view_chapter(chapter_id):
    editing_comment_id = request.args.get('edit_comment_id', type=int)
    
    # 步驟 1: 使用 SQLAlchemy 取得章節物件，get_or_404 會自動處理找不到的情況
    chapter = Chapter.query.get_or_404(chapter_id)
    
    # 步驟 2: 使用 SQLAlchemy 查詢來尋找上一章
    prev_chapter = Chapter.query.filter(
        Chapter.book_id == chapter.book_id,
        Chapter.chapter_number < chapter.chapter_number
    ).order_by(Chapter.chapter_number.desc()).first()

    # 步驟 3: 使用 SQLAlchemy 查詢來尋找下一章
    next_chapter = Chapter.query.filter(
        Chapter.book_id == chapter.book_id,
        Chapter.chapter_number > chapter.chapter_number
    ).order_by(Chapter.chapter_number.asc()).first()

    # 步驟 4: 渲染樣板。可以直接透過 'chapter' 物件取得關聯的書本和留言
    return render_template('chapter.html', 
                           chapter=chapter, 
                           book=chapter.book, # 直接使用 backref
                           comments=chapter.comments, # 直接使用 relationship
                           all_books=get_all_books(), 
                           editing_comment_id=editing_comment_id,
                           prev_chapter_id=prev_chapter.id if prev_chapter else None,
                           next_chapter_id=next_chapter.id if next_chapter else None)
# --- 後台書本 CRUD ---
@app.route('/add_book', methods=['GET', 'POST'])
@auth.login_required
def add_book():
    if request.method == 'POST':
        title = request.form['title']
        author = request.form['author']
        summary = request.form['summary']
        
        if title:
            # 檢查書名是否已存在
            existing_book = Book.query.filter_by(title=title).first()
            if existing_book:
                return "錯誤：書名已存在！請使用不同的書名。"

            # 步驟 1: 根據 Book 模型(class) 建立一個新的 Python 物件
            timestamp = get_current_taipei_time()
            new_book = Book(
                title=title, 
                author=author, 
                summary=summary, 
                created_timestamp=timestamp
            )
            
            # 步驟 2: 將這個新物件加入到資料庫的 session 中
            db.session.add(new_book)
            
            # 步驟 3: 提交 session，將變更寫入資料庫
            db.session.commit()
            
            return redirect(url_for('index'))
            
    # 如果是 GET 請求，就正常顯示頁面
    return render_template('add_book.html', all_books=get_all_books())

@app.route('/book/edit/<int:book_id>', methods=['GET', 'POST'])
@auth.login_required
def edit_book(book_id):
    book = Book.query.get_or_404(book_id)
    if request.method == 'POST':
        # 1. 記錄日誌
        edit_log = BookEditLog(
            book_id=book_id,
            old_title=book.title,
            old_author=book.author,
            old_summary=book.summary,
            edit_timestamp=get_current_taipei_time()
        )
        db.session.add(edit_log)
        
        # 2. 更新書本資訊
        book.title = request.form['title']
        book.author = request.form['author']
        book.summary = request.form['summary']
        
        try:
            db.session.commit()
        except:
            db.session.rollback()
            return "錯誤：書名可能與現有書本重複！"
        
        return redirect(url_for('view_book_toc', book_id=book_id))

    return render_template('edit_book.html', book=book, all_books=get_all_books())

@app.route('/book/logs/<int:book_id>')
@auth.login_required
def view_book_logs(book_id):
    book = Book.query.get_or_404(book_id)
    logs = BookEditLog.query.filter_by(book_id=book_id).order_by(BookEditLog.edit_timestamp.desc()).all()
    return render_template('book_logs.html', book=book, logs=logs, all_books=get_all_books())
    
@app.route('/book/delete/<int:book_id>', methods=['POST'])
@auth.login_required
def delete_book(book_id):
    book = Book.query.get_or_404(book_id)
    db.session.delete(book) # SQLAlchemy 的 cascade 設定會自動刪除所有關聯的章節、留言和日誌
    db.session.commit()
    return redirect(url_for('index'))

@app.route('/book/<int:book_id>/add_chapter', methods=['GET', 'POST'])
@auth.login_required
def add_chapter(book_id):
    # 步驟 1: 使用 SQLAlchemy 的方法取得書本物件，簡潔又安全
    book = Book.query.get_or_404(book_id)

    if request.method == 'POST':
        chapter_number = request.form['chapter_number']
        title = request.form['title']
        content = request.form['content']
        
        if chapter_number and title and content:
            timestamp = get_current_taipei_time()
            
            # 步驟 2: 根據 Chapter 模型(class) 建立一個新的章節物件
            new_chapter = Chapter(
                book_id=book_id,
                chapter_number=int(chapter_number),
                title=title,
                content=content,
                timestamp=timestamp
            )
            
            # 步驟 3: 將新物件加入 session 並提交到資料庫
            db.session.add(new_chapter)
            db.session.commit()
            
            return redirect(url_for('view_book_toc', book_id=book_id))
            
    # 如果是 GET 請求，就正常顯示頁面
    return render_template('add_chapter.html', book=book, all_books=get_all_books())

# --- 【新】章節 CRUD ---
@app.route('/chapter/edit/<int:chapter_id>', methods=['GET', 'POST'])
@auth.login_required
def edit_chapter(chapter_id):
    chapter = Chapter.query.get_or_404(chapter_id)
    if request.method == 'POST':
        # 1. 記錄日誌
        edit_log = ChapterEditLog(chapter_id=chapter_id, old_title=chapter.title, old_content=chapter.content, edit_timestamp=get_current_taipei_time())
        db.session.add(edit_log)
        # 2. 更新章節
        chapter.chapter_number = int(request.form['chapter_number'])
        chapter.title = request.form['title']
        chapter.content = request.form['content']
        db.session.commit()
        return redirect(url_for('view_chapter', chapter_id=chapter_id))
    return render_template('edit_chapter.html', chapter=chapter, book=chapter.book, all_books=get_all_books())

@app.route('/chapter/delete/<int:chapter_id>', methods=['POST'])
@auth.login_required
def delete_chapter(chapter_id):
    chapter = Chapter.query.get_or_404(chapter_id)
    book_id = chapter.book_id
    db.session.delete(chapter) # SQLAlchemy 的 cascade 設定會自動刪除關聯的留言和日誌
    db.session.commit()
    return redirect(url_for('view_book_toc', book_id=book_id))

# --- 【新】留言 CRUD ---
@app.route('/comment/add/<int:chapter_id>', methods=['POST'])
@auth.login_required
def add_comment(chapter_id):
    author = request.form['author']
    content = request.form['content']
    if author and content:
        new_comment = Comment(chapter_id=chapter_id, author=author, content=content, timestamp = get_current_taipei_time())
        db.session.add(new_comment)
        db.session.commit()
    return redirect(url_for('view_chapter', chapter_id=chapter_id) + '#comments-section')

@app.route('/comment/update/<int:comment_id>', methods=['POST'])
@auth.login_required
def update_comment(comment_id):
    comment = Comment.query.get_or_404(comment_id)
    new_content = request.form['content']
    if new_content:
        # 1. 記錄日誌
        edit_log = CommentEditLog(comment_id=comment_id, old_content=comment.content, edit_timestamp = get_current_taipei_time())
        db.session.add(edit_log)
        # 2. 更新留言
        comment.content = new_content
        comment.last_edited_timestamp = get_current_taipei_time()
        db.session.commit()
    return redirect(url_for('view_chapter', chapter_id=comment.chapter_id) + '#comments-section')

@app.route('/comment/delete/<int:comment_id>', methods=['POST'])
@auth.login_required
def delete_comment(comment_id):
    comment = Comment.query.get_or_404(comment_id)
    chapter_id = comment.chapter_id
    db.session.delete(comment) # SQLAlchemy 的 cascade 設定會自動刪除關聯的留言日誌
    db.session.commit()
    return redirect(url_for('view_chapter', chapter_id=chapter_id) + '#comments-section')

# ... 您所有的 CRUD 路由結束後 ...

# --- 【請將這整段全新的程式碼複製到您的 app.py 中】 ---
# 建立一個秘密的一次性管理工具路由
@app.route('/internal-admin/correct-all-timestamps-now')
@auth.login_required # 確保只有登入的使用者才能執行
def run_timestamp_correction():
    """
    透過訪問此網址來觸發一次性的時間校正腳本。
    """
    print("--- 開始透過網頁觸發校正資料庫中的時間戳 ---")
    
    # 從 Python 3.9 開始內建，Render 的環境支援
    from zoneinfo import ZoneInfo
    
    utc_tz = ZoneInfo("UTC")
    taipei_tz = ZoneInfo("Asia/Taipei")

    def convert_utc_string_to_taipei(ts_string):
        if not ts_string: return None
        try:
            naive_dt = datetime.strptime(ts_string, "%Y-%m-%d %H:%M:%S")
            utc_dt = naive_dt.replace(tzinfo=utc_tz)
            taipei_dt = utc_dt.astimezone(taipei_tz)
            return taipei_dt.strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            return ts_string

    tables_and_fields = {
        Book: ['created_timestamp'],
        Chapter: ['timestamp'],
        Comment: ['timestamp', 'last_edited_timestamp'],
        BookEditLog: ['edit_timestamp'],
        ChapterEditLog: ['edit_timestamp'],
        CommentEditLog: ['edit_timestamp']
    }

    log_messages = []
    for model, fields in tables_and_fields.items():
        records = model.query.all()
        log_messages.append(f"正在處理 {model.__tablename__} 表格...")
        count = 0
        for record in records:
            for field in fields:
                old_time_str = getattr(record, field)
                new_time_str = convert_utc_string_to_taipei(old_time_str)
                setattr(record, field, new_time_str)
            count += 1
        log_messages.append(f" -> 完成 {count} 筆紀錄。")

    db.session.commit()
    log_messages.append("\n✅ 所有時間戳已成功校正為 GMT+8！")
    
    # 在瀏覽器上顯示簡單的成功訊息
    return "<pre>" + "\n".join(log_messages) + "</pre>"
# --- 新增程式碼結束 ---

# --- 執行程式 ---
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)


'''

import os
import sqlite3
from flask import Flask, render_template, request, redirect, url_for, g
from datetime import datetime

app = Flask(__name__)
DATABASE = 'novel_site.db'

# --- 【優化 1】資料庫連線管理 ---
# 使用 g (Flask 的全域物件) 來管理資料庫連線，確保每個請求只會連線一次
def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
    return db

# 使用 teardown_appcontext 裝飾器，讓 Flask 在每次請求結束後自動關閉資料庫連線
@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

def init_db():
    with app.app_context():
        db = get_db()
        with open('schema.sql', 'r') as f:
            db.cursor().executescript(f.read())
        db.commit()

# 資料庫結構 (與您提供的一致，這裡保持不變)
with open('schema.sql', 'w') as f:
    f.write("""
    CREATE TABLE IF NOT EXISTS books (
        id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL UNIQUE,
        author TEXT, summary TEXT, created_timestamp TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS chapters (
        id INTEGER PRIMARY KEY AUTOINCREMENT, book_id INTEGER NOT NULL,
        chapter_number INTEGER NOT NULL, title TEXT NOT NULL, content TEXT NOT NULL,
        timestamp TEXT NOT NULL,
        FOREIGN KEY (book_id) REFERENCES books (id)
    );
    CREATE TABLE IF NOT EXISTS chapter_edit_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT, chapter_id INTEGER NOT NULL,
        old_title TEXT NOT NULL, old_content TEXT NOT NULL, edit_timestamp TEXT NOT NULL,
        FOREIGN KEY (chapter_id) REFERENCES chapters (id)
    );
    CREATE TABLE IF NOT EXISTS comments (
        id INTEGER PRIMARY KEY AUTOINCREMENT, chapter_id INTEGER NOT NULL,
        author TEXT NOT NULL, content TEXT NOT NULL, timestamp TEXT NOT NULL,
        last_edited_timestamp TEXT,
        FOREIGN KEY (chapter_id) REFERENCES chapters (id)
    );
    CREATE TABLE IF NOT EXISTS comment_edit_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT, comment_id INTEGER NOT NULL,
        old_content TEXT NOT NULL, edit_timestamp TEXT NOT NULL,
        FOREIGN KEY (comment_id) REFERENCES comments (id)
    );
    """)

def get_all_books():
    # 現在可以直接用 get_db()，不需要自己開關連線
    db = get_db()
    books = db.execute('SELECT id, title FROM books ORDER BY title').fetchall()
    return books

# ... 您的 import ...
from flask_httpauth import HTTPBasicAuth # 【新增】引入認證函式庫
from werkzeug.security import generate_password_hash, check_password_hash #【新增】用於密碼安全

app = Flask(__name__)
auth = HTTPBasicAuth() # 【新增】初始化認證物件

# --- 【修改】從環境變數讀取帳號密碼 ---
# os.environ.get() 會嘗試讀取環境變數，如果找不到，就使用後面的預設值
# 預設值是為了讓您在自己的電腦上 (本機) 測試時也能運作
admin_user = os.environ.get('ADMIN_USERNAME', 'local_user')
admin_pass = os.environ.get('ADMIN_PASSWORD', 'local_password')

users = {
    admin_user: generate_password_hash(admin_pass)
}

# --- 【新增】驗證密碼的函式 ---
@auth.verify_password
def verify_password(username, password):
    if username in users and \
            check_password_hash(users.get(username), password):
        return username

# 請在您「所有」希望被保護的 @app.route(...) 下方，都加上 @auth.login_required 這一行
# 例如：view_chapter, add_book, edit_chapter 等等...

# --- 主要路由 ---
@app.route('/')
@auth.login_required
def index():
    db = get_db()
    books = db.execute('SELECT * FROM books ORDER BY created_timestamp DESC').fetchall()
    
    # --- 【在這裡加入診斷碼】 ---
    all_books_for_nav = get_all_books()
    print("--- 診斷日誌：準備傳遞到前端的 all_books 變數 ---")
    print(all_books_for_nav)
    print("--------------------------------------------------")
    # --- 診斷碼結束 ---
    
    return render_template('index.html', books=books, all_books=get_all_books())

@app.route('/book/<int:book_id>')
@auth.login_required
def view_book_toc(book_id):
    db = get_db()
    book = db.execute('SELECT * FROM books WHERE id = ?', (book_id,)).fetchone()
    if not book: return "書本不存在", 404
    chapters = db.execute('SELECT id, chapter_number, title, timestamp FROM chapters WHERE book_id = ? ORDER BY chapter_number ASC', (book_id,)).fetchall()
    return render_template('book_toc.html', book=book, chapters=chapters, all_books=get_all_books())

@app.route('/chapter/<int:chapter_id>')
@auth.login_required
def view_chapter(chapter_id):
    editing_comment_id = request.args.get('edit_comment_id', type=int)
    db = get_db()
    chapter = db.execute('SELECT * FROM chapters WHERE id = ?', (chapter_id,)).fetchone()
    if not chapter: return "章節不存在", 404
    
    book = db.execute('SELECT id, title FROM books WHERE id = ?', (chapter['book_id'],)).fetchone()
    comments = db.execute('SELECT * FROM comments WHERE chapter_id = ? ORDER BY timestamp ASC', (chapter_id,)).fetchall()
    
    prev_chapter = db.execute('SELECT id FROM chapters WHERE book_id = ? AND chapter_number < ? ORDER BY chapter_number DESC LIMIT 1', (chapter['book_id'], chapter['chapter_number'])).fetchone()
    next_chapter = db.execute('SELECT id FROM chapters WHERE book_id = ? AND chapter_number > ? ORDER BY chapter_number ASC LIMIT 1', (chapter['book_id'], chapter['chapter_number'])).fetchone()

    return render_template('chapter.html', 
                           chapter=chapter, book=book, comments=comments, 
                           all_books=get_all_books(), editing_comment_id=editing_comment_id,
                           prev_chapter_id=prev_chapter['id'] if prev_chapter else None,
                           next_chapter_id=next_chapter['id'] if next_chapter else None)
    
# --- 後台書本 CRUD ---
@app.route('/add_book', methods=['GET', 'POST'])
@auth.login_required
def add_book():
    if request.method == 'POST':
        title = request.form['title']
        author = request.form['author']
        summary = request.form['summary']
        if title:
            db = get_db()
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            try:
                db.execute('INSERT INTO books (title, author, summary, created_timestamp) VALUES (?, ?, ?, ?)',
                           (title, author, summary, timestamp))
                db.commit()
            except sqlite3.IntegrityError:
                return "錯誤：書名已存在！"
            return redirect(url_for('index'))
    return render_template('add_book.html', all_books=get_all_books())

# --- 請將這整個函式複製到您的 app.py 中 ---

@app.route('/book/edit/<int:book_id>', methods=['GET', 'POST'])
@auth.login_required
def edit_book(book_id):
    db = get_db()
    # 先取得要編輯的書本資料，確保它存在
    book = db.execute('SELECT * FROM books WHERE id = ?', (book_id,)).fetchone()
    if not book:
        return "書本不存在", 404

    # 如果是表單提交 (POST)，就處理更新邏輯
    if request.method == 'POST':
        new_title = request.form['title']
        new_author = request.form['author']
        new_summary = request.form['summary']
        if new_title:
            try:
                db.execute('UPDATE books SET title = ?, author = ?, summary = ? WHERE id = ?',
                           (new_title, new_author, new_summary, book_id))
                db.commit()
                # 更新成功後，跳轉回該書的目錄頁
                return redirect(url_for('view_book_toc', book_id=book_id))
            except sqlite3.IntegrityError:
                # 如果新書名與其他書本重複，會引發這個錯誤
                return "錯誤：書名已存在！"
    
    # 如果是第一次進入頁面 (GET)，就顯示編輯表單
    return render_template('edit_book.html', book=book, all_books=get_all_books())

@app.route('/book/delete/<int:book_id>', methods=['POST'])
@auth.login_required
def delete_book(book_id):
    """刪除一本書及其所有相關的章節、留言和日誌"""
    db = get_db()
    
    # 步驟 1: 找出這本書底下所有的章節 ID
    chapters = db.execute('SELECT id FROM chapters WHERE book_id = ?', (book_id,)).fetchall()
    if chapters:
        chapter_ids = [row['id'] for row in chapters]
        
        # 步驟 2: 根據章節 ID 刪除所有相關的留言和留言日誌
        # 使用 IN 子句可以一次刪除多筆
        # 我們需要生成對應數量的佔位符 (?, ?, ?)
        placeholders = ', '.join(['?'] * len(chapter_ids))
        
        # 刪除留言的編輯日誌
        comment_ids_to_delete = db.execute(f'SELECT id FROM comments WHERE chapter_id IN ({placeholders})', chapter_ids).fetchall()
        if comment_ids_to_delete:
            c_ids = [row['id'] for row in comment_ids_to_delete]
            c_placeholders = ', '.join(['?'] * len(c_ids))
            db.execute(f'DELETE FROM comment_edit_logs WHERE comment_id IN ({c_placeholders})', c_ids)

        # 刪除留言
        db.execute(f'DELETE FROM comments WHERE chapter_id IN ({placeholders})', chapter_ids)
        
        # 刪除章節的編輯日誌
        db.execute(f'DELETE FROM chapter_edit_logs WHERE chapter_id IN ({placeholders})', chapter_ids)

    # 步驟 3: 刪除這本書的所有章節
    db.execute('DELETE FROM chapters WHERE book_id = ?', (book_id,))
    
    # 步驟 4: 最後，刪除書本本身
    db.execute('DELETE FROM books WHERE id = ?', (book_id,))
    
    db.commit()
    db.close()
    
    print(f"已成功刪除書本 ID: {book_id} 及其所有相關資料。")
    return redirect(url_for('index'))

@app.route('/book/<int:book_id>/add_chapter', methods=['GET', 'POST'])
@auth.login_required
def add_chapter(book_id):
    db = get_db()
    book = db.execute('SELECT id, title FROM books WHERE id = ?', (book_id,)).fetchone()
    if not book: return "書本不存在", 404

    if request.method == 'POST':
        chapter_number = request.form['chapter_number']
        title = request.form['title']
        content = request.form['content']
        if chapter_number and title and content:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            db.execute('INSERT INTO chapters (book_id, chapter_number, title, content, timestamp) VALUES (?, ?, ?, ?, ?)',
                       (book_id, int(chapter_number), title, content, timestamp))
            db.commit()
            return redirect(url_for('view_book_toc', book_id=book_id))
    
    return render_template('add_chapter.html', book=book, all_books=get_all_books())


@app.route('/chapter/edit/<int:chapter_id>', methods=['GET', 'POST'])
@auth.login_required
def edit_chapter(chapter_id):
    db = get_db()
    chapter = db.execute('SELECT * FROM chapters WHERE id = ?', (chapter_id,)).fetchone()
    if not chapter:
        return "章節不存在", 404
    
    if request.method == 'POST':
        # 從表單取得所有需要的欄位
        new_chapter_number = request.form['chapter_number']
        new_title = request.form['title']
        new_content = request.form['content']

        if new_title and new_content and new_chapter_number:
            # 1. 記錄日誌
            edit_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            db.execute('INSERT INTO chapter_edit_logs (chapter_id, old_title, old_content, edit_timestamp) VALUES (?, ?, ?, ?)',
                       (chapter_id, chapter['title'], chapter['content'], edit_timestamp))
            
            # 2. 更新章節 (包含章節編號)
            db.execute('UPDATE chapters SET chapter_number = ?, title = ?, content = ? WHERE id = ?',
                       (int(new_chapter_number), new_title, new_content, chapter_id))
            db.commit()
            return redirect(url_for('view_chapter', chapter_id=chapter_id))
    
    # 如果是 GET 請求，就顯示編輯頁面
    book = db.execute('SELECT id, title FROM books WHERE id = ?', (chapter['book_id'],)).fetchone()
    return render_template('edit_chapter.html', chapter=chapter, book=book, all_books=get_all_books())

@app.route('/chapter/delete/<int:chapter_id>', methods=['POST'])
@auth.login_required
def delete_chapter(chapter_id):
    db = get_db()
    # 查找章節屬於哪本書，以便刪除後跳轉回目錄頁
    chapter = db.execute('SELECT book_id FROM chapters WHERE id = ?', (chapter_id,)).fetchone()
    if chapter:
        book_id = chapter['book_id']
        # 刪除章節、相關日誌和留言
        db.execute('DELETE FROM comments WHERE chapter_id = ?', (chapter_id,))
        db.execute('DELETE FROM chapter_edit_logs WHERE chapter_id = ?', (chapter_id,))
        db.execute('DELETE FROM chapters WHERE id = ?', (chapter_id,))
        db.commit()
        db.close()
        return redirect(url_for('view_book_toc', book_id=book_id))
    db.close()
    return redirect(url_for('index'))

# --- 留言 CRUD ---
@app.route('/comment/add/<int:chapter_id>', methods=['POST'])
@auth.login_required
def add_comment(chapter_id):
    author = request.form['author']
    content = request.form['content']
    if author and content:
        db = get_db()
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        db.execute('INSERT INTO comments (chapter_id, author, content, timestamp) VALUES (?, ?, ?, ?)',
                   (chapter_id, author, content, timestamp))
        db.commit()
        db.close()
    return redirect(url_for('view_chapter', chapter_id=chapter_id) + '#comments-section')

@app.route('/comment/update/<int:comment_id>', methods=['POST'])
@auth.login_required
def update_comment(comment_id):
    new_content = request.form['content']
    chapter_id = request.form['chapter_id'] # 需要從表單中傳遞 chapter_id
    if new_content and chapter_id:
        db = get_db()
        old_comment = db.execute('SELECT content FROM comments WHERE id = ?', (comment_id,)).fetchone()
        edit_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        db.execute('INSERT INTO comment_edit_logs (comment_id, old_content, edit_timestamp) VALUES (?, ?, ?)',
                   (comment_id, old_comment['content'], edit_timestamp))
        db.execute('UPDATE comments SET content = ?, last_edited_timestamp = ? WHERE id = ?',
                   (new_content, edit_timestamp, comment_id))
        db.commit()
        db.close()
    return redirect(url_for('view_chapter', chapter_id=chapter_id) + '#comments-section')

@app.route('/comment/delete/<int:comment_id>', methods=['POST'])
@auth.login_required
def delete_comment(comment_id):
    chapter_id = request.form['chapter_id'] # 同樣需要 chapter_id
    if chapter_id:
        db = get_db()
        db.execute('DELETE FROM comment_edit_logs WHERE comment_id = ?', (comment_id,))
        db.execute('DELETE FROM comments WHERE id = ?', (comment_id,))
        db.commit()
        db.close()
    return redirect(url_for('view_chapter', chapter_id=chapter_id) + '#comments-section')

# --- 執行程式 ---
if __name__ == '__main__':
    if not os.path.exists(DATABASE):
        init_db()
    app.run(debug=True)
    '''