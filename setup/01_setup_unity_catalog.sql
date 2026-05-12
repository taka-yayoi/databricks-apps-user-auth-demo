-- =================================================================
-- Databricks Apps 認可モデル比較デモ用 Unity Catalog セットアップ
--
-- このスクリプトは、行フィルターを使ったテーブルを作成し、
-- アプリ認可（SP）とユーザー認可で異なる結果が返ることを再現します。
--
-- 実行前提:
--   - main への CREATE SCHEMA 権限 ( 他のカタログを使う場合は置換 )
--   - SQL Warehouse へのアクセス
-- =================================================================

USE CATALOG main;

-- スキーマ作成
CREATE SCHEMA IF NOT EXISTS main.app_auth_demo
COMMENT 'Databricks Apps 認可モデル比較デモ';

USE SCHEMA main.app_auth_demo;

-- -----------------------------------------------------------------
-- 1. ユーザー → 可視リージョン のマッピングテーブル
-- -----------------------------------------------------------------
-- ここに登録されたユーザーだけがデータを見える設計。
-- アプリ専用 SP は登録されないので、SP として実行すると 0 行になる。
CREATE OR REPLACE TABLE user_region_map (
  user_email STRING NOT NULL,
  allowed_region STRING NOT NULL
);

-- ⚠️ 自分のメールアドレスに書き換えてください
INSERT INTO user_region_map VALUES
  ('your.email@example.com', 'APAC'),
  ('teammate1@example.com', 'EMEA'),
  ('teammate2@example.com', 'AMER');

-- -----------------------------------------------------------------
-- 2. デモ用売上テーブル
-- -----------------------------------------------------------------
CREATE OR REPLACE TABLE sales_data (
  order_id BIGINT,
  region STRING,
  customer STRING,
  amount DOUBLE,
  order_date DATE
);

INSERT INTO sales_data VALUES
  (1,  'APAC', 'Tokyo Trading Co.',     12000.0, DATE'2026-01-15'),
  (2,  'APAC', 'Singapore Holdings',     8500.0, DATE'2026-01-20'),
  (3,  'APAC', 'Sydney Logistics',      15200.0, DATE'2026-01-22'),
  (4,  'EMEA', 'Berlin GmbH',           22000.0, DATE'2026-01-25'),
  (5,  'EMEA', 'London Inc',            15000.0, DATE'2026-02-01'),
  (6,  'EMEA', 'Paris SARL',            18500.0, DATE'2026-02-03'),
  (7,  'AMER', 'NY Holdings',           30000.0, DATE'2026-02-05'),
  (8,  'AMER', 'SF Tech',               18000.0, DATE'2026-02-10'),
  (9,  'AMER', 'Toronto Industries',    21000.0, DATE'2026-02-12');

-- -----------------------------------------------------------------
-- 3. 行フィルター関数
-- -----------------------------------------------------------------
-- 現在の実行 ID（current_user）が user_region_map に登録された
-- allowed_region に一致する行だけを可視にする。
CREATE OR REPLACE FUNCTION region_row_filter(region STRING)
RETURNS BOOLEAN
RETURN region IN (
  SELECT allowed_region
  FROM main.app_auth_demo.user_region_map
  WHERE user_email = current_user()
);

ALTER TABLE sales_data SET ROW FILTER region_row_filter ON (region);

-- -----------------------------------------------------------------
-- 4. アプリ専用サービスプリンシパルへの権限付与
-- -----------------------------------------------------------------
-- アプリ認可（SP）でクエリできるようにするための最低限の権限。
-- ⚠️ '<APP_SERVICE_PRINCIPAL_APPLICATION_ID>' をアプリ詳細画面の
-- 「Authorization」タブで確認した値に置き換えてください。
--
-- 例:
-- GRANT USE CATALOG ON CATALOG main TO `<APP_SERVICE_PRINCIPAL_APPLICATION_ID>`;
-- GRANT USE SCHEMA  ON SCHEMA main.app_auth_demo TO `<APP_SERVICE_PRINCIPAL_APPLICATION_ID>`;
-- GRANT SELECT      ON TABLE main.app_auth_demo.sales_data TO `<APP_SERVICE_PRINCIPAL_APPLICATION_ID>`;
-- GRANT SELECT      ON TABLE main.app_auth_demo.user_region_map TO `<APP_SERVICE_PRINCIPAL_APPLICATION_ID>`;

-- -----------------------------------------------------------------
-- 動作確認: それぞれの ID で実行して結果を比較する
-- -----------------------------------------------------------------
-- SELECT current_user();
-- SELECT * FROM sales_data ORDER BY order_id;
