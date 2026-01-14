-- schema.sql
CREATE TABLE IF NOT EXISTS users (
  id           BIGINT PRIMARY KEY,
  firebase_uid TEXT UNIQUE NOT NULL,
  email        TEXT UNIQUE NOT NULL
);

CREATE TABLE IF NOT EXISTS stocks (
  stock_id   TEXT PRIMARY KEY,
  stock_name TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS user_stocks (
  user_id  BIGINT NOT NULL,
  stock_id TEXT NOT NULL,
  PRIMARY KEY (user_id, stock_id),
  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
  FOREIGN KEY (stock_id) REFERENCES stocks(stock_id) ON DELETE CASCADE
);
