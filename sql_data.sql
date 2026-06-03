DROP TABLE IF EXISTS article_tags;
DROP TABLE IF EXISTS bookmarks;
DROP TABLE IF EXISTS notes;
DROP TABLE IF EXISTS work_articles;
DROP TABLE IF EXISTS articles;
DROP TABLE IF EXISTS works;
DROP TABLE IF EXISTS tags;
DROP TABLE IF EXISTS users;

CREATE TABLE users (
    user_id SERIAL PRIMARY KEY,
    username VARCHAR(100) NOT NULL
);

CREATE TABLE works (
    work_id SERIAL PRIMARY KEY,
    title VARCHAR(200) NOT NULL,
    type VARCHAR(50),
    release_date DATE,
    status VARCHAR(50),
    description TEXT,
    source_url TEXT
);

CREATE TABLE articles (
    article_id SERIAL PRIMARY KEY,
    title VARCHAR(300) NOT NULL,
    source_name VARCHAR(100),
    source_url TEXT,
    published_at DATE,
    summary TEXT,
    category VARCHAR(100)
);

CREATE TABLE work_articles (
    work_id INT REFERENCES works(work_id) ON DELETE CASCADE,
    article_id INT REFERENCES articles(article_id) ON DELETE CASCADE,
    PRIMARY KEY (work_id, article_id)
);

CREATE TABLE tags (
    tag_id SERIAL PRIMARY KEY,
    tag_name VARCHAR(100) UNIQUE NOT NULL
);

CREATE TABLE article_tags (
    article_id INT REFERENCES articles(article_id) ON DELETE CASCADE,
    tag_id INT REFERENCES tags(tag_id) ON DELETE CASCADE,
    PRIMARY KEY (article_id, tag_id)
);

CREATE TABLE bookmarks (
    bookmark_id SERIAL PRIMARY KEY,
    user_id INT REFERENCES users(user_id) ON DELETE CASCADE,
    article_id INT REFERENCES articles(article_id) ON DELETE CASCADE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE notes (
    note_id SERIAL PRIMARY KEY,
    user_id INT REFERENCES users(user_id) ON DELETE CASCADE,
    article_id INT REFERENCES articles(article_id) ON DELETE CASCADE,
    note_text TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);