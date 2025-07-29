
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
    