import json
import os
import random
import sys

import chromadb
import streamlit as st

class User:
    def __init__(self, name: str, choices: list[int], comment: str) -> None:
        self.name = name
        self.choices = choices
        self.comment = comment if comment else "無回答"

    def distance(self, user: "User") -> float:
        d = sum([(s - u) ** 2 for s, u in zip(self.choices, user.choices)])
        return d

class DB:
    def __init__(self, dirname: str, collection_name: str) -> None:
        self.chroma_client = chromadb.PersistentClient(path=os.path.join(os.path.dirname(__file__), dirname))
        self.collection = self.chroma_client.get_or_create_collection(collection_name)
    
    def upsert(self, user_id, user: User) -> None:
        self.collection.upsert(
            ids=[str(user_id)],
            embeddings=user.choices,
            metadatas={"name": user.name},
            documents=user.comment
        )
    
    def generate_id(self) -> int:
        available_ids = set(range(1, 1000)).difference(self.collection.peek(limit=sys.maxsize)["ids"])
        user_id = random.choice(tuple(available_ids))
        return user_id
    
    def get(self, user_id: int) -> User | None:
        result = self.collection.get(
            ids=[str(user_id)], 
            include=["embeddings", "metadatas", "documents"]
        )

        if len(result["ids"]) == 0:
            return None
        
        name = result["metadatas"][0]["name"]
        choices = result["embeddings"][0].tolist()
        text = result["documents"][0]

        return User(name, choices, text)
    
    def search(self, user: User) -> tuple[User, float]:
        if self.collection.count() < 2:
            return None, -1.0
        
        result = self.collection.query(
            query_embeddings=user.choices,
            n_results=2,
            include=["embeddings", "metadatas", "documents", "distances"]
        )

        name = result["metadatas"][0][1]["name"]
        choices = result["embeddings"][0][1].tolist()
        comment = result["documents"][0][1]
        distance = result["distances"][0][1]

        return User(name, choices, comment), distance

class Question:
    def __init__(self, text: str, choices: tuple) -> None:
        self.text = text
        self.choices = choices
    
    def choice_index(self, choice: str) -> int | None:
        if choice in self.choices:
            return self.choices.index(choice)
        else:
            return None
    
    @classmethod
    def load_questions(cls, filename: str) -> list["Question"]:
        file_path = os.path.join(os.path.dirname(__file__), filename)
        with open(file_path, mode="r", encoding="utf-8") as f:
            j = json.load(f)

        return [cls(q["text"], q["choices"]) for q in j]

def init_session() -> None:
    db_dir = "data"
    db_name = "fes"
    questions = Question.load_questions("questions.json")

    st.session_state["questions"] = questions
    st.session_state["db"] = DB(db_dir, db_name)
    st.session_state["name"] = ""
    st.session_state["choices"] = [None for _ in range(len(questions))]
    st.session_state["comment"] = ""
    st.session_state["user_id"] = 0
    st.session_state["init"] = True

@st.dialog("あ！")
def aleart(message: str) -> None:
    st.write(message)

def register_page() -> None:
    st.subheader("ユーザー登録")

    st.session_state["name"] = st.text_input(label="**ニックネーム**", value=st.session_state["name"], placeholder="※他の人が見る可能性があります")

    questions = st.session_state["questions"]
    choices = st.session_state["choices"]
    for i in range(len(questions)):
        q = questions[i]
        c = choices[i]
        st.session_state["choices"][i] = q.choice_index(st.radio(f"**{q.text}**", q.choices, index=c))

    st.session_state["comment"] = st.text_area("**フリーコメント**", value=st.session_state["comment"], max_chars=300, placeholder="自由に書いてね")

    if st.button("回答！"):
        if not st.session_state["name"]:
            aleart("ニックネームを入力してください")
        elif st.session_state["choices"].count(None) > 0:
            aleart("回答していない設問があります")
        else:
            user_id = st.session_state["user_id"]
            if user_id == 0:
                user_id = st.session_state["db"].generate_id()
                st.session_state["user_id"] = user_id
                st.sidebar.write(f"あなたのID: **{user_id}**")
                message = f"登録しました。  \nあなたのID: {user_id}"
            else:
                message = "更新しました。"

            user = User(st.session_state["name"], st.session_state["choices"], st.session_state["comment"])
            st.session_state["db"].upsert(user_id, user)
            st.session_state["user"] = user

            aleart(message)

def print_result(user: User, distance: float) -> None:
    max_distance = 4 ** 2 * len(st.session_state["questions"])
    num_message = 8
    if distance == 0.0:
        d = "0mm"
        m = "もはや相手とあなたは同一人物。クローン。ドッペルゲンガー。消滅しないよう気を付けてください。"
    elif distance < 1 / (num_message - 2) * max_distance:
        d = "2cm"
        m = "かなり相性がいいです！生涯気が合うこと間違いなしです。結婚おめでとうございます。"
    elif distance < 2 / (num_message - 2) * max_distance:
        d = "30cm"
        m = "近い性格をしています。普段打ち明けられないようなことも話してみてはどうでしょうか？"
    elif distance < 3 / (num_message - 2) * max_distance:
        d = "2m"
        m = "ほどよい距離間です。でもこれくらいの距離感がいいんですよね。みんなちがってみんないい。"
    elif distance < 4 / (num_message - 2) * max_distance:
        d = "10m"
        m = "知り合いくらい。あんまりパーソナルなことはまだ言えない距離感。これから仲良くなっていこう。"
    elif distance < 5 / (num_message - 2) * max_distance:
        d = "120m"
        m = "本当に仲良しなの…？"
    elif distance < 6 / (num_message - 2) * max_distance:
        d = "5km"
        m = "・・・。"
    else:
        d = "1億光年"
        m = "すごいです！あなたと相手は対極に位置しています。太陽と月。光と影。始まりと終わり。アダムとイヴとして世界を創造しましょう。"

    st.write(f"見つかった相手: **{user.name}**")
    st.subheader(f"あなたとの距離: **{d}**")
    st.write(m)
    st.subheader("相手の回答")
    with st.container(border=True):
        st.write(f"**ニックネーム**  \n{user.name}")
        for q, a in zip(st.session_state["questions"], user.choices):
            st.write(f"**{q.text}**  \n{q.choices[int(a)]}")
        st.write(f"**フリーコメント**  \n{user.comment}")

def search_page() -> None:
    st.subheader("検索")

    f = st.form("search")
    c1, c2 = f.columns([1, 1], vertical_alignment="bottom")
    search_query = c1.text_input("**ユーザーID**")
    button = c2.form_submit_button("検索！")

    if button:
        if st.session_state["user_id"] == 0:
            aleart("先にユーザー登録をしてね・・・！")
        elif search_query:
            result_user = st.session_state["db"].get(search_query)
            if not result_user is None:
                print_result(result_user, st.session_state["user"].distance(result_user))
            else:
                st.write("ユーザーが見つかりませんでした")
        else:
            aleart("ユーザーIDを入力してください")

def matching_page() -> None:
    st.subheader("マッチング")

    st.write("↓ボタンを押してマッチング↓")
    if st.button("マッチング！"):
        if st.session_state["user_id"] == 0:
            aleart("先にユーザー登録をしてね・・・！")
        else:
            result_user, distance = st.session_state["db"].search(st.session_state["user"])
            if not result_user is None:
                print_result(result_user, distance)
            else:
                st.write("あなた以外に登録ユーザーがいません。こんなアプリに頼るのはやめて自力で頑張りましょう。")

def main() -> None:
    st.set_page_config("超☆マッチングアプリ", layout="wide")

    if not "init" in st.session_state:
        init_session()
        
    st.title("超☆相性診断")
    st.write("あなたと心の距離が近い人を探してくれます。  \n質問に答えたらサイドバー（左上の`>`アイコン）から検索してみましょう！  \n※ブラウザをリロードすると入力した情報は消えるので注意してください")
    
    page = st.sidebar.radio("**ページ選択**", ["ユーザー登録", "検索", "マッチング"])
    st.sidebar.markdown("---")
    if st.session_state["user_id"] > 0:
        st.sidebar.write(f"あなたのID: **{st.session_state['user_id']}**")
    
    if page == "ユーザー登録":
        register_page()
    elif page == "検索":
        search_page()
    elif page == "マッチング":
        matching_page()

main()
