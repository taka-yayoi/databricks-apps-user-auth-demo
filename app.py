"""
Databricks Apps 認可モデル比較デモ

アプリ認可（Service Principal）とユーザー認可（On-Behalf-Of）の
振る舞いの違いを、同じテーブル・同じクエリで並べて確認するためのアプリ。
"""
import os
import streamlit as st
import pandas as pd
from databricks import sql
from databricks.sdk import WorkspaceClient
from databricks.sdk.core import Config

# -------------------------------------------------------------------
# 環境設定
# -------------------------------------------------------------------
HTTP_PATH_RAW = os.getenv("DATABRICKS_WAREHOUSE_HTTP_PATH")
DEMO_TABLE = os.getenv("DEMO_TABLE", "main.app_auth_demo.sales_data")

cfg = Config()  # Databricks Apps の実行環境では SP の資格情報を自動検出


def resolve_http_path(raw: str | None) -> str | None:
    """Databricks Apps の valueFrom が warehouse ID を返すか、
    フル HTTP path を返すかは状況次第なので、両対応する。"""
    if not raw:
        return None
    if raw.startswith("/"):
        return raw  # 既にフルパス
    return f"/sql/1.0/warehouses/{raw}"  # ID とみなしてパスを組み立て


HTTP_PATH = resolve_http_path(HTTP_PATH_RAW)


def make_user_client(user_token: str) -> WorkspaceClient:
    """ユーザー認可用の WorkspaceClient を生成。

    Databricks Apps 環境では DATABRICKS_CLIENT_ID/SECRET が常に設定されており、
    そのまま WorkspaceClient(token=...) すると
    "more than one authorization method configured: oauth and pat"
    で落ちる。auth_type='pat' を明示して OAuth を無視させる。
    """
    return WorkspaceClient(
        host=cfg.host,
        token=user_token,
        auth_type="pat",
    )

st.set_page_config(
    page_title="認可モデル比較デモ",
    page_icon="🔐",
    layout="wide",
)

# -------------------------------------------------------------------
# HTTPヘッダーから「アプリにフォワードされたユーザー情報」を取得
# -------------------------------------------------------------------
# Databricks Apps はユーザー認可スコープが設定されているとき、
# 各リクエストの HTTP ヘッダーにユーザー ID/トークンを差し込む。
headers = st.context.headers if hasattr(st.context, "headers") else {}

user_access_token = headers.get("x-forwarded-access-token")
user_email = headers.get("x-forwarded-email")
user_username = headers.get("x-forwarded-preferred-username")
user_user_id = headers.get("x-forwarded-user")

# -------------------------------------------------------------------
# UI
# -------------------------------------------------------------------
st.title("🔐 Databricks Apps 認可モデル比較デモ")
st.markdown(
    "**アプリ認可（Service Principal）** と **ユーザー認可（On-Behalf-Of User）** を"
    "並べて比較できるアプリです。同じテーブルに同じクエリを実行して、"
    "結果がどう変わるかを体験してください。"
)

# サイドバーに設定値を表示
with st.sidebar:
    st.subheader("⚙️ 接続設定")
    st.text(f"Host: {cfg.host}")
    if HTTP_PATH:
        st.text(f"Warehouse HTTP Path:\n{HTTP_PATH}")
        if HTTP_PATH != HTTP_PATH_RAW:
            st.caption(f"(ID `{HTTP_PATH_RAW}` から組み立て)")
    else:
        st.error("Warehouse HTTP Path: None")
        st.caption(
            "App resources で SQL warehouse を追加し、"
            "Resource key を `sql_warehouse` にしてアプリを再起動してください。"
        )
    st.text(f"Demo Table: {DEMO_TABLE}")
    st.divider()
    st.subheader("🧰 アプリ環境変数")
    st.text(f"DATABRICKS_CLIENT_ID: "
            f"{'✓ set' if os.getenv('DATABRICKS_CLIENT_ID') else '✗ missing'}")
    st.text(f"DATABRICKS_CLIENT_SECRET: "
            f"{'✓ set' if os.getenv('DATABRICKS_CLIENT_SECRET') else '✗ missing'}")

tab_id, tab_query, tab_scope, tab_headers, tab_doc = st.tabs(
    ["👤 認証ID", "📊 クエリ比較", "🔑 スコープ動作確認", "📋 ヘッダー検査", "📚 解説"]
)


# ===================================================================
# Tab 1: 「同じ API を叩いても返ってくる ID が違う」を見せる
# ===================================================================
with tab_id:
    st.subheader("`current_user.me()` を 2 つの認可で呼ぶ")
    st.caption("同じ SDK 呼び出しでも、認可方式によって"
               "「誰として」実行されるかが変わります。")

    col_app, col_user = st.columns(2)

    with col_app:
        st.markdown("### 🤖 アプリ認可（SP）")
        st.caption("環境変数 `DATABRICKS_CLIENT_ID` / `DATABRICKS_CLIENT_SECRET`"
                   " から OAuth M2M で認証")
        try:
            w_sp = WorkspaceClient()  # 環境変数から SP を自動検出
            me = w_sp.current_user.me()
            st.success(f"認証ID: **{me.user_name}**")
            st.json({
                "id": me.id,
                "user_name": me.user_name,
                "display_name": me.display_name,
                "active": me.active,
            })
        except Exception as e:
            st.error(f"エラー: {e}")

    with col_user:
        st.markdown("### 🙋 ユーザー認可（代理）")
        st.caption("HTTPヘッダー `x-forwarded-access-token` を使って"
                   " OAuth U2M で認証")
        if not user_access_token:
            st.warning(
                "ユーザートークンが届いていません。\n\n"
                "原因: アプリにユーザー認可スコープが設定されていない、"
                "またはアプリの再起動が必要です。"
            )
        else:
            try:
                w_user = make_user_client(user_access_token)
                me = w_user.current_user.me()
                st.success(f"認証ID: **{me.user_name}**")
                st.json({
                    "id": me.id,
                    "user_name": me.user_name,
                    "display_name": me.display_name,
                    "active": me.active,
                })
            except Exception as e:
                st.error(f"エラー: {e}")

    st.divider()
    st.info(
        "💡 **ここがポイント**: 左は常にアプリ専用 SP として動き、"
        "右はアプリを開いているユーザーとして動きます。"
        "Unity Catalog の権限評価もこの ID で行われます。"
    )


# ===================================================================
# Tab 2: 同じクエリでも結果が変わる（Row Filter / Column Mask）
# ===================================================================
with tab_query:
    st.subheader("同じクエリを 2 つの認可で実行")
    st.caption("行フィルターが現在の認証 ID に応じて"
               "自動的に適用される様子を確認します。")

    query = st.text_area(
        "実行する SQL",
        value=f"SELECT * FROM {DEMO_TABLE} ORDER BY order_id",
        height=80,
    )

    if not HTTP_PATH:
        st.error("環境変数 `DATABRICKS_WAREHOUSE_HTTP_PATH` が未設定です。"
                 " app.yaml で SQL Warehouse のリソースを設定してください。")
    elif st.button("クエリを実行", type="primary"):
        col_app, col_user = st.columns(2)

        # --- アプリ認可で実行 ---
        with col_app:
            st.markdown("### 🤖 アプリ認可（SP）として実行")
            try:
                conn = sql.connect(
                    server_hostname=cfg.host,
                    http_path=HTTP_PATH,
                    credentials_provider=lambda: cfg.authenticate,
                )
                with conn.cursor() as cur:
                    cur.execute(query)
                    df = cur.fetchall_arrow().to_pandas()
                st.metric("取得行数", len(df))
                st.dataframe(df, use_container_width=True)
                conn.close()
            except Exception as e:
                st.error(f"エラー: {e}")

        # --- ユーザー認可で実行 ---
        with col_user:
            st.markdown("### 🙋 ユーザー認可として実行")
            if not user_access_token:
                st.warning("ユーザートークンが届いていません。"
                           "ユーザー認可スコープ `sql` を有効化してください。")
            else:
                try:
                    conn = sql.connect(
                        server_hostname=cfg.host,
                        http_path=HTTP_PATH,
                        access_token=user_access_token,
                    )
                    with conn.cursor() as cur:
                        cur.execute(query)
                        df = cur.fetchall_arrow().to_pandas()
                    st.metric("取得行数", len(df))
                    st.dataframe(df, use_container_width=True)
                    conn.close()
                except Exception as e:
                    st.error(f"エラー: {e}")

        st.divider()
        st.info(
            "💡 **ここがポイント**: テーブルに Row Filter が掛かっていると、"
            "左（SP）はマッピング未登録のため 0 行、"
            "右（ユーザー）は自分の region のみ可視という違いが出ます。"
        )


# ===================================================================
# Tab 3: スコープを越える API 呼び出しがどう失敗するか
# ===================================================================
with tab_scope:
    st.subheader("スコープによるアクセス制御")
    st.caption("ユーザー認可は app.yaml で宣言したスコープに限定されます。"
               "範囲外の API は呼び出せません。")

    if not user_access_token:
        st.warning("ユーザートークンが届いていません。"
                   "ユーザー認可スコープを有効化してください。")
    else:
        st.markdown("以下のボタンで各 API を**ユーザー認可で**呼び出し、"
                    "成功/失敗を確認します。")

        col1, col2, col3 = st.columns(3)

        with col1:
            if st.button("👤 `iam.current-user:read`\nme() を呼ぶ"):
                try:
                    w = make_user_client(user_access_token)
                    me = w.current_user.me()
                    st.success(f"OK: {me.user_name}")
                except Exception as e:
                    st.error(f"NG: {e}")

        with col2:
            if st.button("🗂️ `files.files`\nVolume 一覧"):
                try:
                    w = make_user_client(user_access_token)
                    catalogs = [c.name for c in w.catalogs.list()][:5]
                    st.success(f"OK: {catalogs}")
                except Exception as e:
                    st.error(f"NG: {e}")

        with col3:
            if st.button("🤖 `serving.serving-endpoints`\nエンドポイント一覧"):
                try:
                    w = make_user_client(user_access_token)
                    eps = [e.name for e in w.serving_endpoints.list()][:5]
                    st.success(f"OK: {eps}")
                except Exception as e:
                    st.error(f"NG (スコープ未付与の場合エラー): {e}")

        st.divider()
        st.info(
            "💡 **ここがポイント**: app.yaml で `serving.serving-endpoints` を"
            "宣言していなければ、ユーザー自身が権限を持っていても"
            "アプリからの呼び出しはブロックされます（最小権限の原則）。"
        )


# ===================================================================
# Tab 4: 実際に届いている x-forwarded-* ヘッダーを覗く
# ===================================================================
with tab_headers:
    st.subheader("Databricks Apps が転送するヘッダー")
    st.caption("ユーザー認可が有効なとき、各リクエストには"
               "ユーザー ID・トークン・グループなどがヘッダーで届きます。")

    interesting = {
        k: v for k, v in headers.items()
        if k.lower().startswith("x-forwarded")
        or k.lower().startswith("x-request")
        or k.lower() in ("user-agent",)
    }

    if not interesting:
        st.warning("x-forwarded-* ヘッダーが見つかりませんでした。"
                   "ユーザー認可が無効、もしくは未デプロイの可能性があります。")
    else:
        # トークンはセキュリティのため伏字
        masked = {}
        for k, v in interesting.items():
            if "token" in k.lower():
                masked[k] = f"{v[:8]}...({len(v)} chars)" if v else None
            else:
                masked[k] = v
        st.json(masked)

    st.warning(
        "⚠️ アクセストークンはログ・print・例外メッセージに"
        "**絶対に**含めないでください。ベストプラクティスに従ってください。"
    )


# ===================================================================
# Tab 5: 解説
# ===================================================================
with tab_doc:
    st.markdown("""
### 2 つの認可モデル

| 観点 | アプリ認可（SP） | ユーザー認可（OBO） |
|---|---|---|
| 認証主体 | アプリ専用 SP | アプリを開いているユーザー |
| OAuth フロー | M2M（Client Credentials） | U2M（On-Behalf-Of） |
| 資格情報の取得元 | 環境変数 `DATABRICKS_CLIENT_ID/SECRET` | HTTPヘッダー `x-forwarded-access-token` |
| Unity Catalog 権限評価 | SP の権限 | ユーザーの権限 |
| 行フィルター | SP に対して評価 | ユーザーに対して評価 |
| 用途 | 共有処理・バックグラウンド | ユーザー個別データ |
| 範囲制御 | サービスプリンシパルの権限のみ | スコープで API を制限 |

### ユーザー認可が有効になる条件

1. ワークスペース管理者がユーザー認可機能を有効化していること
2. アプリにスコープを追加していること（例: `sql`, `dashboards.genie`, `files.files`）
3. スコープ追加後にアプリを再起動していること
4. ユーザーが初回アクセス時に同意していること

### よく使うスコープ

| スコープ | 用途 |
|---|---|
| `iam.current-user:read` | 自分の情報を読む（既定） |
| `iam.access-control:read` | アクセス制御を読む（既定） |
| `sql` | SQL Warehouse 経由でクエリ実行 |
| `dashboards.genie` | Genie Space を操作 |
| `files.files` | Files API でファイル・ボリュームを操作 |
| `serving.serving-endpoints` | Serving Endpoint を呼び出す |

### 参考リンク

- [Databricks Apps で承認を構成する（日本語ドキュメント）](https://learn.microsoft.com/ja-jp/azure/databricks/dev-tools/databricks-apps/auth)
- [Databricks Apps の HTTPヘッダー](https://learn.microsoft.com/ja-jp/azure/databricks/dev-tools/databricks-apps/http-headers)
- [Unity Catalog の行フィルター](https://learn.microsoft.com/ja-jp/azure/databricks/tables/row-and-column-filters)
""")
