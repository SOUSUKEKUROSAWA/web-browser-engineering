from typing import Union
import tkinter
import tkinter.font
import socket
import ssl

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

def print_tree(node: Union[Text, Element], indent=0):
    print(" " * indent, node)
    for child in node.children:
        print_tree(child, indent + 2)

class HTMLParser:
    SELF_CLOSING_TAGS = ["area","base","br","col","embed","hr","img","input","link","meta","param","source","track","wbr",]
    HEAD_TAGS = ["base", "basefont", "bgsound", "noscript", "link", "meta", "title", "style", "script"]
    """<head> 要素に入れるべきタグのリスト"""

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

    def add_text(self, text: str):
        """
        テキストトークンをノードに変換する．

        note: テキストトークンに子ノードは存在しえないので，その場で完成させる．
        """
        if text.isspace(): return

        # タグが書かれず、いきなりテキストから始まる場合を考慮
        self.implicit_tags(None)

        parent = self.unfinished[-1]
        node = Text(text, parent)
        parent.children.append(node)

    def add_tag(self, tag: str):
        tag, attributes = self.get_attributes(tag)

        # <!DOCTYPE html> や <!-- comment --> は無視する．
        if tag.startswith("!"): return

        self.implicit_tags(tag)

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

    def implicit_tags(self, tag):
        """
        暗黙的なタグ挿入

        param:
            tag: 現在パースしているタグ名．テキストノードの場合は None．
        """
        while True:
            open_tags = [node.tag for node in self.unfinished]
            if open_tags == [] and tag != "html":
                # ドキュメントの最初のタグが <html> 以外の場合
                self.add_tag("html")
            elif open_tags == ["html"] and tag not in ["head", "body", "/html"]:
                if tag in self.HEAD_TAGS:
                    self.add_tag("head")
                else:
                    self.add_tag("body")
            elif open_tags == ["html", "head"] and tag not in ["/head"] + self.HEAD_TAGS:
                # パーサーが <head> ないにあり，<body> に入れるべき要素を見た場合
                self.add_tag("/head")
            else:
                break

    def finish(self) -> Element:
        """
        残った未完成ノードを完成させる（＝ タグを閉じる）．

        return: ツリーの頂点となる単一の要素
        """
        if not self.unfinished:
            # 中身が完全に空（または空白文字だけ）の場合を考慮
            self.implicit_tags(None)

        while len(self.unfinished) > 1:
            node = self.unfinished.pop()
            parent = self.unfinished[-1]
            parent.children.append(node)
        return self.unfinished.pop()

FONTS = {}
"""フォントキャッシュ"""

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

WIDTH = 800
"""キャンバス全体の幅"""
HEIGHT = 600
"""キャンバス全体の高さ"""
HSTEP = 13
"""画面上の1文字の幅"""
VSTEP = 18
"""画面上の1文字の高さ"""

BLOCK_ELEMENTS = ["html", "body", "article", "section", "nav", "aside", "h1", "h2", "h3", "h4", "h5", "h6", "hgroup", "header", "footer", "address", "p", "hr", "pre", "blockquote", "ol", "ul", "menu", "li", "dl", "dt", "dd", "figure", "figcaption", "main", "div", "table", "form", "fieldset", "legend", "details", "summary"]

class DocumentLayout:
    """
    レイアウトツリーのルート
    """

    def __init__(self, node):
        self.node = node
        """HTML ツリー"""
        self.parent = None
        self.children = []

    def layout(self):
        """
        HTMLツリーからレイアウトツリーを構築する．
        """
        child = BlockLayout(self.node, self, None)
        self.children.append(child)
        self.width = WIDTH - 2*HSTEP # 2*HSTEP は左右のパディング
        self.x = HSTEP
        self.y = VSTEP # 上下のパディング
        # 「note: width と height の計算順」と同じ理由で，height の計算は child.layout() の後に行う必要がある．
        child.layout()
        self.height = child.height

    def paint(self):
        return []

class BlockLayout:
    def __init__(self, node: Element, parent, previous):
        self.node = node
        """
        HTMLツリー
        """
        # e.g.
        # HTML ツリー                 レイアウトツリー
        #                             Document
        # html                    ->  |-- Block
        # |-- body                ->      |-- Block
        #     |-- h1              ->          |-- Block
        #     |   |- Text                     |
        #     |-- p               ->          |-- Block
        #         |-- Text
        #         |-- a
        #         |   |-- Text
        #         |-- Text
        #
        # 例えば，HTMLツリーとして解析は必要だが，
        # 描画はしない head タグなどはレイアウトツリーには含まれないなど，使い分けが可能
        self.parent: BlockLayout = parent
        self.previous: BlockLayout = previous
        """１つ前の（兄弟の）レイアウトオブジェクト"""
        self.children: list[BlockLayout] = []
        self.display_list = []
        """ページ座標やフォント情報を保持するリスト"""
        self.x = None
        self.y = None
        self.width = None
        self.height = None
        self.cursor_x = 0
        """self.x に対する相対位置"""
        self.cursor_y = 0
        """self.y に対する相対位置"""

    def layout_mode(self):
        if isinstance(self.node, Text):
            return "inline"
        elif any([isinstance(child, Element) and child.tag in BLOCK_ELEMENTS for child in self.node.children]):
            # エッジケース: <div><p>paragraph</p>text<b>bold</b></div> など
            return "block"
        elif self.node.children:
            return "inline"
        else:
            return "block"

    def layout(self):
        """
        HTMLツリーからレイアウトツリーを構築する．
        """
        # スタイルを考慮しなければ，x, width は親と共通
        self.x = self.parent.x
        self.width = self.parent.width

        # 垂直位置 y は前の兄弟要素の有無で位置が決まる．
        if self.previous:
            self.y = self.previous.y + self.previous.height
        else:
            self.y = self.parent.y

        mode = self.layout_mode()
        if mode == "block":
            previous = None
            for child in self.node.children:
                # HTML ツリーの子をレイアウトツリーの子に変換して登録する．
                next = BlockLayout(child, self, previous)
                self.children.append(next)
                previous = next
        else:
            self.cursor_x = 0
            self.cursor_y = 0
            self.weight = "normal"
            self.style = "roman"
            self.size = 12
            self.line: list[tuple[int, str, tkinter.font.Font]] = []
            """行バッファ"""

            self.recurse(self.node)

            # 最終行のフォーマット
            self.flush()

        # note: width と height の計算順
        #   width: 親ブロックの幅が「あらかじめ」計算されている必要がある．＝ layout() の再帰呼び出しの「前」に計算する必要がある．
        #   height: 子ブロックの高さが「あらかじめ」計算されている必要がある．＝ layout() の再帰呼び出しの「後」に計算する必要がある．
        for child in self.children:
            child.layout()

        if mode == "block":
            # 全ての子を含むのに十分な高さが必要．
            self.height = sum([child.height for child in self.children])
        else:
            self.height = self.cursor_y

    def recurse(self, tree: Union[Text, Element]):
        """
        インライン要素を再帰的にレイアウトする（ディスプレイリストを構築する）．
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
        if tag == "i":
            self.style = "roman"
        elif tag == "b":
            self.weight = "normal"
        elif tag == "small":
            self.size += 2
        elif tag == "big":
            self.size -= 4
        elif tag == "p":
            self.flush()
            self.cursor_y += VSTEP # 段落間のスペースを追加

    def flush(self):
        """
        改行の前処理

        その行のベースラインの計算と，改行後のカーソル位置の計算．
        """
        if not self.line: return # 空の行はスキップ

        # ベースラインに沿って単語を整列させる（テキストのサイズが異なるとバラバラになってしまうため）
        max_ascent = max([font.metrics("ascent") for x, word, font in self.line]) # 行内のテキストの最大アセント（高さ）
        baseline = self.cursor_y + 1.25 * max_ascent
        for rel_x, word, font in self.line:
            x = self.x + rel_x
            y = self.y + baseline - font.metrics("ascent") # ベースラインからアセント（高さ）の分だけ上が，このテキストの左上になる．
            self.display_list.append((x, y, word, font))

        # 次の行の x, y 座標をセット
        metrics = [font.metrics() for x, word, font in self.line]
        max_descent = max([metric["descent"] for metric in metrics]) # 行内のテキストの最大ディセント（g や y などの文字の下側のはみ出し部分の深さ）
        self.cursor_y = baseline + 1.25 * max_descent
        self.cursor_x = 0
        self.line = [] # バッファをクリア

    def word(self, word):
        """
        個々の単語のディスプレイリストを作成する．
        """
        font = get_font(self.size, self.weight, self.style)
        w = font.measure(word) # 英語は単語ごとにサイズが異なるので，都度幅を計算する．

        if self.cursor_x + w > self.width:
            # 折り返し
            self.flush()

        # その行のディスプレイリストをバッファに追加
        self.line.append((self.cursor_x, word, font))

        # x カーソルを次の単語まで移動
        self.cursor_x += w + font.measure(" ")

    def paint(self):
        cmds = []

        # コード例に使用される pre タグの背景をグレーにする．
        # warning: テキストは背景の上に描画される必要があるので，DrawText より DrawRect が前に来る必要がある．
        if isinstance(self.node, Element) and self.node.tag == "pre":
            x2, y2 = self.x + self.width, self.y + self.height
            rect = DrawRect(self.x, self.y, x2, y2, "gray")
            cmds.append(rect)

        if self.layout_mode() == "inline":
            for x, y, word, font in self.display_list:
                cmds.append(DrawText(x, y, word, font))

        # node.style は style() 内で動的に追加されている属性なので，ここで検証．
        assert hasattr(self.node, "style") and isinstance(self.node.style, dict)
        bgcolor = self.node.style.get("background-color", "transparent")

        if bgcolor != "transparent":
            x2, y2 = self.x + self.width, self.y + self.height
            rect = DrawRect(self.x, self.y, x2, y2, bgcolor)
            cmds.append(rect)

        return cmds

class DrawText:
    """
    テキストを描画するためのコマンド
    """

    def __init__(self, x1, y1, text, font: tkinter.font.Font):
        self.top = y1
        self.left = x1
        self.text = text
        self.font = font
        self.bottom = y1 + font.metrics("linespace")

    def execute(self, scroll, canvas: tkinter.Canvas):
        """
        parameter:
            scroll: スクロール量
        """
        canvas.create_text(
            self.left,
            self.top - scroll,
            text=self.text,
            font=self.font,
            anchor='nw'
        )

class DrawRect:
    """
    背景を描画するためのコマンド
    """
    def __init__(self, x1, y1, x2, y2, color):
        self.top = y1
        self.left = x1
        self.bottom = y2
        self.right = x2
        self.color = color

    def execute(self, scroll, canvas: tkinter.Canvas):
        """
        parameter:
            scroll: スクロール量
        """
        canvas.create_rectangle(
            self.left,
            self.top - scroll,
            self.right,
            self.bottom - scroll,
            width=0, # 境界線不要なので 0
            fill=self.color
        )

def paint_tree(layout_object: Union[BlockLayout, DocumentLayout], display_list: list):
    """
    レイアウトツリー全体のディスプレイリストを構築する．
    """
    display_list.extend(layout_object.paint())
    for child in layout_object.children:
        paint_tree(child, display_list)

SCROLL_STEP = 100
"""1回の画面スクロールで座標が移動する距離"""

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
        """画面座標(y)の一番上がページ座標(y)のどこに位置するのかを表すオフセット値"""
        self.window.bind("<Down>", self.scrolldown) # 下矢印キーがクリックされたら，scrolldown メソッドが呼ばれる．

    def draw(self):
        """
        描画対象（テキストや背景など）の画面座標を決定し，画面（キャンバス）に描画する．

        ページ座標：Webページ全体における位置座標
        画面座標：画面（フレーム）内における位置座標

        e.g. ページ座標(y) 123 ピクセルの位置のテキストが 30 ピクセル下にスクロールされた場合の画面座標(y)は 93 ピクセル．
        """
        self.canvas.delete("all") # 再描画時のためにまずキャンバスをクリア．
        for cmd in self.display_list:
            if cmd.top > self.scroll + HEIGHT: continue # 画面下部より下の文字
            if cmd.bottom < self.scroll: continue # 画面上部より上の文字

            cmd.execute(self.scroll, self.canvas)

    def load(self, url: URL):
        body = url.request()
        self.nodes = HTMLParser(body).parse()
        style(self.nodes)
        self.document = DocumentLayout(self.nodes)
        self.document.layout()
        self.display_list: list[Union[DrawText, DrawRect]] = []
        """ページ座標やフォント情報を保持するリスト"""
        paint_tree(self.document, self.display_list)
        self.draw()

    def scrolldown(self, e):
        """
        note:
            最下部を過ぎてスクロールはできない．
        """
        # 最下部までスクロールした状態とは，
        # 「画面の下端」=「ドキュメント全体の最下部」
        # => self.scroll + HEIGHT == self.document.height + 2*VSTEP
        # => self.scroll == self.document.height + 2*VSTEP - HEIGHT
        max_y = max(self.document.height + 2*VSTEP - HEIGHT, 0)
        self.scroll = min(self.scroll + SCROLL_STEP, max_y) # self.scroll + SCROLL_STEP => 次のスクロール位置
        self.draw() # 再描画

class CSSParser:
    def __init__(self, s):
        self.s: list[str] = s
        """パース対象のテキスト"""
        self.i = 0
        """パーサの現在位置"""

    def whitespace(self):
        """
        空白を読み飛ばす（パーサのインデックスだけ進める）．
        """
        while self.i < len(self.s) and self.s[self.i].isspace():
            self.i += 1

    def word(self) -> str:
        """
        プロパティをパースする．

        return:
            プロパティ名やその値
        """
        start = self.i

        while self.i < len(self.s):
            if self.s[self.i].isalnum() or self.s[self.i] in "#-.%":
                # プロパティとして許容されている文字である場合
                self.i += 1
            else:
                break

        if not (self.i > start):
            raise Exception("Parsing error")

        return self.s[start:self.i]

    def literal(self, literal):
        """
        リテラルを読み飛ばす（コロン「:」など）．
        """
        if not (self.i < len(self.s) and self.s[self.i] == literal):
            raise Exception("Parsing error")
        self.i += 1

    def pair(self):
        """
        プロパティ名とその値のペアをパースする．

        return:
            プロパティ名
            プロパティ値
        """
        prop = self.word()
        self.whitespace()
        self.literal(":")
        self.whitespace()
        val = self.word()

        return prop.casefold(), val

    def body(self):
        """
        style 属性全体をパースする．
        """
        pairs = {}

        while self.i < len(self.s):
            try:
                prop, val = self.pair()
                pairs[prop.casefold()] = val
                self.whitespace()
                self.literal(";")
                self.whitespace()
            except Exception:
                why = self.ignore_until([";"])
                if why == ";":
                    self.literal(";")
                    self.whitespace()
                else:
                    break

        return pairs

    def ignore_until(self, chars: list[str]):
        """
        chars で指定された文字までスキップする．

        e.g. パースに失敗した場合，パースできないプロパティと値のペアはスキップして，
             次のパース可能な文字列まで移動して，エラーから復帰するのに使用する．

        return:
            chars で指定された文字列のうち，最初に現れた文字
        """
        while self.i < len(self.s):
            if self.s[self.i] in chars:
                return self.s[self.i]
            else:
                self.i += 1

        return None

def style(node):
    """
    パースされた style 属性をノードの style フィールドに保存する．
    """
    node.style = {}
    if isinstance(node, Element) and "style" in node.attributes:
        pairs = CSSParser(node.attributes["style"]).body()
        for property, value in pairs.items():
            node.style[property] = value

    for child in node.children:
        style(child)

if __name__ == "__main__":
    import sys
    Browser().load(URL(sys.argv[1]))
    tkinter.mainloop()
