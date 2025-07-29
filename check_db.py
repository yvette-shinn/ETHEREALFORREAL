import sqlite3
import os

DATABASE = 'novel_site.db'

print(f"--- 正在檢查資料庫檔案 '{DATABASE}' ---")

if not os.path.exists(DATABASE):
    print(f"‼️ 錯誤：在目前目錄下找不到 {DATABASE} 檔案！")
else:
    try:
        # 連接到資料庫
        con = sqlite3.connect(DATABASE)
        con.row_factory = sqlite3.Row # 讓我們可以用欄位名稱存取資料
        cur = con.cursor()

        # 查詢 books 資料表中的所有內容
        books = cur.execute("SELECT * FROM books").fetchall()

        con.close()

        if not books:
            print("‼️ 結果：'books' 資料表中沒有找到任何資料！")
            print("-> 請確認您是否已經成功執行過『新增書本』的操作。")
        else:
            print(f"✅ 成功找到 {len(books)} 本書：")
            for book in books:
                print(f"  - ID: {book['id']}, 書名: {book['title']}")

    except Exception as e:
        print(f"❌ 讀取資料庫時發生錯誤: {e}")
        print("-> 這可能表示資料庫檔案已損壞，或 schema.sql 結構有問題。")

print("--- 檢查完畢 ---")