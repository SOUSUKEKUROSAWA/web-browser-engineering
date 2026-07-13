from typing import Union
import tkinter
import tkinter.font
import socket
import ssl

WIDTH = 800
"""キャンバス全体の幅"""
HEIGHT = 600
"""キャンバス全体の高さ"""
HSTEP = 13
"""画面上の1文字の幅"""
VSTEP = 18
"""画面上の1文字の高さ"""
SCROLL_STEP = 100
"""1回の画面スクロールで座標が移動する距離"""
FONTS = {}
"""フォントキャッシュ"""

class URL:
    def __init__(self, url: str):
        # URL のパース．
        self.scheme, url = url.split("://", 1)
        assert self.scheme in ["http", "https"]

        if self.scheme == "http":
            self.port = 80
        elif self.scheme == "https":
            self.port = 443

        if "/" not in url:
            url = url + "/"

        self.host, url = url.split("/", 1)
        self.path = "/" + url

        if ":" in self.host:
            # http://example.org:8080/ のようなカスタムポートに対応．
            self.host, port = self.host.split(":", 1)
            self.port = int(port)

    def request(self):
        # ソケットの作成．
        s = socket.socket(
            family=socket.AF_INET, # アドレスファミリー（＝ 他のコンピュータを見つける方法）．INET（＝ IPv4 を使用）．
            type=socket.SOCK_STREAM, # ソケットタイプ（＝ 行われる会話の種類）．STREAM（＝ 任意の量のデータを送信できる）．
            proto=socket.IPPROTO_TCP, # プロトコル（＝ 2台のコンピュータが接続を確立する方法）．
        )
        s.connect((self.host, self.port))
        if self.scheme == "https":
            ctx = ssl.create_default_context()
            s = ctx.wrap_socket(s, server_hostname=self.host)

        # リクエストの送信．
        request = "GET {} HTTP/1.0\r\n".format(self.path)
        request += "Host: {}\r\n".format(self.host)
        request += "\r\n"
        s.send(request.encode("utf8"))

        # レスポンスの受信．
        response = s.makefile("r", encoding="utf8", newline="\r\n") # レスポンスのバイトストリームを1つのファイルオブジェクトにまとめて返す．

        # レスポンスのパース（1行目）．
        statusline = response.readline()
        version, status, explanation = statusline.split(" ", 2)

        # レスポンスのパース（ヘッダー）．
        response_headers = {}
        while True:
            line = response.readline()
            if line == "\r\n": break
            header, value = line.split(":", 1)
            response_headers[header.casefold()] = value.strip() # casefold(): 小文字に正規化．strip(): 前後の空白を削除．

        assert "transfer-encoding" not in response_headers
        assert "content-encoding" not in response_headers

        # レスポンスのパース（ボディ）．
        content = response.read()
        s.close()

        return content

class Browser:
    def __init__(self):
        self.window = tkinter.Tk()
        self.canvas = tkinter.Canvas(
            self.window,
            width=WIDTH,
            height=HEIGHT
        )
        self.canvas.pack()
        self.scroll = 0
        self.window.bind("<Down>", self.scrolldown) # 下矢印キーがクリックされたら，scrolldown メソッドが呼ばれる．

    def draw(self):
        """
        テキストの画面座標を決定し，画面（キャンバス）に描画する．

        ページ座標：Webページ全体における位置座標
        画面座標：画面（フレーム）内における位置座標

        e.g. ページ座標(y) 123 ピクセルの位置のテキストが 30 ピクセル下にスクロールされた場合の画面座標(y)は 93 ピクセル．
        """
        self.canvas.delete("all") # 再描画時のためにまずキャンバスをクリア．
        for x, y, word, font in self.display_list:
            if y > self.scroll + HEIGHT: continue # 画面下部より下の文字
            if y + VSTEP < self.scroll: continue # 画面上部より上の文字

            self.canvas.create_text(
                x,
                y - self.scroll, # 左上が（0,0）右下が（x,y）となる座標系．
                text=word,
                font=font,
                anchor="nw" # north west の略．左上の角を（0,0）として描画する．
            )

    def load(self, url: URL):
        body = url.request()
        self.nodes = HTMLParser(body).parse()
        self.display_list = Layout(self.nodes).display_list
        self.draw()

    def scrolldown(self, e):
        self.scroll += SCROLL_STEP
        self.draw() # 再描画

class Text:
    def __init__(self, text, parent):
        self.text: str = text
        self.children = [] # note: テキストノードに子は存在しないが，Element との一貫性のために定義している．
        self.parent = parent

    def __repr__(self):
        return repr(self.text)

class Element:
    def __init__(self, tag, attributes, parent):
        self.tag = tag
        self.attributes = attributes
        self.children: list[Union[Text, Element]] = []
        self.parent = parent

    def __repr__(self):
        return "<" + self.tag + ">"

class Layout:
    def __init__(self, tree: Element):
        self.display_list = []
        """ページ座標やフォント情報を保持するリスト"""
        self.cursor_x = HSTEP
        self.cursor_y = VSTEP
        self.weight = "normal"
        self.style = "roman"
        self.size = 12
        self.line: list[tuple[int, str, tkinter.font.Font]] = []
        """行バッファ"""

        self.recurse(tree)

        # 最終行のフォーマット
        self.flush()

    def flush(self):
        """
        改行の前処理

        その行のベースラインの計算と，改行後のカーソル位置の計算．
        """
        if not self.line: return # 空の行はスキップ

        # ベースラインに沿って単語を整列させる（テキストのサイズが異なるとバラバラになってしまうため）
        max_ascent = max([font.metrics("ascent") for x, word, font in self.line]) # 行内のテキストの最大アセント（高さ）
        baseline = self.cursor_y + 1.25 * max_ascent
        for x, word, font in self.line:
            y = baseline - font.metrics("ascent") # ベースラインからアセント（高さ）の分だけ上が，このテキストの左上になる．
            self.display_list.append((x, y, word, font))

        # 次の行の x, y 座標をセット
        metrics = [font.metrics() for x, word, font in self.line]
        max_descent = max([metric["descent"] for metric in metrics]) # 行内のテキストの最大ディセント（g や y などの文字の下側のはみ出し部分の深さ）
        self.cursor_y = baseline + 1.25 * max_descent
        self.cursor_x = HSTEP
        self.line = [] # バッファをクリア

    def recurse(self, tree: Union[Text, Element]):
        """
        ツリーを再帰的にパースする．
        """
        if isinstance(tree, Text):
            for word in tree.text.split():
                self.word(word)
        else:
            self.open_tag(tree.tag)
            for child in tree.children:
                self.recurse(child)
            self.close_tag(tree.tag)

    def open_tag(self, tag):
        if tag == "i":
            self.style = "italic"
        elif tag == "b":
            self.weight = "bold"
        elif tag == "small":
            self.size -= 2
        elif tag == "big":
            self.size += 4
        elif tag == "br":
            self.flush()

    def close_tag(self, tag):
        if tag == "/i":
            self.style = "roman"
        elif tag == "/b":
            self.weight = "normal"
        elif tag == "/small":
            self.size += 2
        elif tag == "/big":
            self.size -= 4
        elif tag == "/p":
            self.flush()
            self.cursor_y += VSTEP # 段落間のスペースを追加

    def token(self, tok):
        if isinstance(tok, Text):
            for word in tok.text.split():
                self.word(word)
        elif isinstance(tok, Element):
            if tok.tag == "i":
                self.style = "italic"
            elif tok.tag == "/i":
                self.style = "roman"
            elif tok.tag == "b":
                self.weight = "bold"
            elif tok.tag == "/b":
                self.weight = "normal"
            elif tok.tag == "small":
                self.size -= 2
            elif tok.tag == "/small":
                self.size += 2
            elif tok.tag == "big":
                self.size += 4
            elif tok.tag == "/big":
                self.size -= 4
            elif tok.tag == "br":
                self.flush()
            elif tok.tag == "/p":
                self.flush()
                self.cursor_y += VSTEP # 段落間のスペースを追加

    def word(self, word):
        """
        個々の単語のディスプレイリストを作成する．
        """
        font = get_font(self.size, self.weight, self.style)
        w = font.measure(word) # 英語は単語ごとにサイズが異なるので，都度幅を計算する．

        if self.cursor_x + w > WIDTH - HSTEP:
            # 折り返し
            self.flush()

        # その行のディスプレイリストをバッファに追加
        self.line.append((self.cursor_x, word, font))

        # x カーソルを次の単語まで移動
        self.cursor_x += w + font.measure(" ")

class HTMLParser:
    SELF_CLOSING_TAGS = ["area","base","br","col","embed","hr","img","input","link","meta","param","source","track","wbr",]

    def __init__(self, body):
        self.body = body
        """分析している HTML 本文"""
        self.unfinished: list[Union[Text, Element]] = []
        """未完成の HTML ツリー"""

    def parse(self) -> Element:
        """
        HTML 本文を HTML ツリー（DOM）に変換する．

        return: ツリーの頂点となる単一の要素
        """
        text = "" # テキストを一時的に保持しておくバッファ．
        in_tag = False
        for c in self.body:
            if c == "<":
                in_tag = True
                if text: self.add_text(text)
                text = ""
            elif c == ">":
                in_tag = False
                self.add_tag(text)
                text = ""
            else:
                text += c
        if not in_tag and text:
            self.add_text(text)
        return self.finish()

    def add_text(self, text: str):
        """
        テキストトークンをノードに変換する．

        note: テキストトークンに子ノードは存在しえないので，その場で完成させる．
        """
        if text.isspace(): return

        parent = self.unfinished[-1]
        node = Text(text, parent)
        parent.children.append(node)

    def add_tag(self, tag: str):
        tag, attributes = self.get_attributes(tag)

        # <!DOCTYPE html> や <!-- comment --> は無視する．
        if tag.startswith("!"): return

        if tag.startswith("/"): # 終了タグ
            # ドキュメントの最後の終了タグは，追加する未完成ノードがないのでスキップ．
            if len(self.unfinished) == 1: return
            # そのノードを完成させる（＝ 自分より内側にいるノードを子ノードとして登録する）
            node = self.unfinished.pop()
            parent = self.unfinished[-1]
            parent.children.append(node)
        elif tag in self.SELF_CLOSING_TAGS: # 自己終了タグ
            parent = self.unfinished[-1]
            node = Element(tag, attributes, parent)
            parent.children.append(node)
        else: # 開始タグ
            parent = self.unfinished[-1] if self.unfinished else None # ドキュメントの最初の開始タグは，親がいないので None．
            node = Element(tag, attributes, parent)
            self.unfinished.append(node)

    def finish(self) -> Element:
        """
        残った未完成ノードを完成させる．

        return: ツリーの頂点となる単一の要素
        """
        while len(self.unfinished) > 1:
            node = self.unfinished.pop()
            parent = self.unfinished[-1]
            parent.children.append(node)
        return self.unfinished.pop()

    def get_attributes(self, text: str):
        """
        タグを，タグ名と属性に分割する．
        """
        parts = text.split()
        tag = parts[0].casefold()
        attributes = {}
        for attrpair in parts[1:]:
            if "=" in attrpair: # e.g. <a href=https://example.com>
                key, value = attrpair.split("=", 1)
                if len(value) > 2 and value[0] in ["'", "\""]: # e.g. <a href="https://example.com>"
                    value = value[1:-1]
                attributes[key.casefold()] = value
            else: # e.g. <input disabled>
                attributes[attrpair.casefold()] = ""
        return tag, attributes

def get_font(size, weight, style) -> tkinter.font.Font:
    """
    フォントキャッシュからフォントを取得，または作成する．
    """
    key = (size, weight, style)
    if key not in FONTS:
        font = tkinter.font.Font(
            size=size,
            weight=weight,
            slant=style
        )
        label = tkinter.Label(font=font)
        FONTS[key] = (font, label) # metrics のパフォーマンス向上のために label を付与（tkinter の推奨）

    return FONTS[key][0]

def print_tree(node: Union[Text, Element], indent=0):
    print(" " * indent, node)
    for child in node.children:
        print_tree(child, indent + 2)

if __name__ == "__main__":
    import sys
    Browser().load(URL(sys.argv[1]))
    tkinter.mainloop()
