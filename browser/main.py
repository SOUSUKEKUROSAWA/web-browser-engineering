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

    def resolve(self, url: str):
        """
        相対URLを完全なURLに変換する．
        """
        # 通常のURL
        if "://" in url: return URL(url)

        # パス相対URL：スラッシュで始まらず，ファイル名のように解決される．
        if not url.startswith("/"):
            dir, _ = self.path.rsplit("/", 1) # e.g. /blog/posts/article.html -> dir: /blog/posts, _: article.html
            while url.startswith("../"):
                _, url = url.split("/", 1) # 先頭の ../ を削る．e.g. ../../index.html -> _: ../, url: ../index.html
                if "/" in dir:
                    dir, _ = dir.rsplit("/", 1) # ディレクトリを1階層上に遡る．e.g. 元の dir が /blog/posts だった場合，dir が /blog に更新される．
            url = dir + "/" + url

        # スキーム相対URL：「//」で始まり，その後に完全なURLが続く．
        if url.startswith("//"):
            return URL(self.scheme + ":" + url)
        # ホスト相対URL：スラッシュで始まるが，既存のスキームとホストを再利用する．
        else:
            return URL(self.scheme + "://" + self.host + ":" + str(self.port) + url)

class Text:
    def __init__(self, text, parent):
        self.text: str = text
        self.children = [] # note: テキストノードに子は存在しないが，Element との一貫性のために定義している．
        self.parent: Element = parent
        self.style = {}

    def __repr__(self):
        return repr(self.text)

class Element:
    def __init__(self, tag, attributes: dict, parent):
        self.tag = tag
        self.attributes = attributes
        self.children: list[Union[Text, Element]] = []
        self.parent: Union[Element, None] = parent
        self.style = {}

    def __repr__(self):
        return "<" + self.tag + ">"

def print_tree(node: Union[Text, Element], indent=0):
    print(" " * indent, node)
    for child in node.children:
        print_tree(child, indent + 2)

def tree_to_list(tree: Union[Element, 'DocumentLayout', 'BlockLayout'], list: list):
    """
    ツリー（HTMLツリー or レイアウトツリー）をノードのリストに変換する．
    """
    list.append(tree)
    for child in tree.children:
        tree_to_list(child, list)
    return list

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

    def literal(self, literal):
        """
        リテラルを読み飛ばす（コロン「:」など）．
        """
        if not (self.i < len(self.s) and self.s[self.i] == literal):
            raise Exception("Parsing error")
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

    def selector(self):
        """
        セレクタをパースする．

        e.g. article div { ... } の article div の部分．
        """
        out = TagSelector(self.word().casefold())
        self.whitespace()
        while self.i < len(self.s) and self.s[self.i] != "{":
            tag = self.word()
            descendant = TagSelector(tag.casefold())
            out = DescendantSelector(out, descendant)
            self.whitespace()
        return out

    def body(self):
        """
        style 属性全体をパースする．

        e.g. article div { font-size: 20px, color: red } の font-size: 20px, color: red の部分．
        """
        pairs = {}

        while self.i < len(self.s) and self.s[self.i] != "}":
            try:
                prop, val = self.pair()
                pairs[prop.casefold()] = val
                self.whitespace()
                self.literal(";")
                self.whitespace()
            except Exception:
                why = self.ignore_until([";", "}"])
                if why == ";":
                    self.literal(";")
                    self.whitespace()
                else:
                    break

        return pairs

    def parse(self):
        """
        .css 形式のテキストをパースして，セレクタとスタイル設定のルールのペアを返す．
        """
        rules = []

        while self.i < len(self.s):
            try:
                self.whitespace()
                selector = self.selector()
                self.literal("{")
                self.whitespace()
                body = self.body()
                self.literal("}")
                rules.append((selector, body))
            except Exception:
                why = self.ignore_until(["}"])
                if why == "}":
                    self.literal("}")
                    self.whitespace()
                else:
                    break

        return rules

class TagSelector:
    """
    タグセレクタ

    e.g. div { ... } // 全ての div 要素をセレクト
    """
    def __init__(self, tag):
        self.tag = tag
        self.priority = 1
        """カスケード順（スタイルルールの適用優先順位）"""

    def matches(self, node: Union[Text, Element]) -> bool:
        """
        セレクタが要素に一致するかどうか
        """
        return isinstance(node, Element) and self.tag == node.tag

class DescendantSelector:
    """
    子孫セレクタ

    e.g. article div { ... } // article を祖先にもつ全ての div 要素をセレクト
    """
    def __init__(self, ancestor: Union[TagSelector, 'DescendantSelector'], descendant: Union[TagSelector, 'DescendantSelector']):
        self.ancestor: Union[TagSelector, DescendantSelector] = ancestor
        """
        祖先のセレクタ

        e.g. article div { ... } の article
        """
        self.descendant: Union[TagSelector, DescendantSelector] = descendant
        """
        子孫のセレクタ

        e.g. article div { ... } の div
        """
        self.priority = ancestor.priority + descendant.priority
        """カスケード順（スタイルルールの適用優先順位）"""

    def matches(self, node: Union[Text, Element]) -> bool:
        """
        セレクタが要素に一致するかどうか
        """
        if not self.descendant.matches(node): return False

        while node.parent:
            if self.ancestor.matches(node.parent): return True
            node = node.parent

        return False

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

DEFAULT_STYLE_SHEET = CSSParser(open("browser.css").read()).parse()

INHERITED_PROPERTIES = {
    "font-size": "16px",
    "font-style": "normal",
    "font-weight": "normal",
    "color": "black",
}

def style(node: Union[Text, Element], rules: list[tuple[Union[TagSelector, DescendantSelector], dict[str, str]]]):
    """
    パースされた style 属性を HTML ツリーの各ノードの style フィールドに保存する．
    """
    for property, default_value in INHERITED_PROPERTIES.items():
        if node.parent:
            node.style[property] = node.parent.style[property]
        else:
            node.style[property] = default_value

    # スタイルシートで定義されたスタイルを設定する．
    for selector, body in rules:
        if not selector.matches(node): continue

        for property, value in body.items():
            node.style[property] = value

    # style 属性で定義されたスタイルはスタイルシートで定義されたスタイルを上書きする．
    if isinstance(node, Element) and "style" in node.attributes:
        pairs = CSSParser(node.attributes["style"]).body()
        for property, value in pairs.items():
            node.style[property] = value

    # 計算済みスタイル: font-size の継承は，％表示を絶対的なピクセル単位に解決してから継承する．
    if str(node.style["font-size"]).endswith("%"):
        if node.parent:
            parent_font_size = node.parent.style["font-size"]
        else:
            # エッジケース: ルートの html 要素の％は，デフォルトのフォントサイズに対する相対値を意味する．
            parent_font_size = INHERITED_PROPERTIES["font-size"]

        node_pct = float(node.style["font-size"][:-1]) / 100 # e.g. "50%" -> 0.5
        parent_px = float(parent_font_size[:-2]) # e.g. "16px" -> 16.0
        node.style["font-size"] = str(node_pct * parent_px) + "px"

    for child in node.children:
        style(child, rules)

def cascade_priority(rule: tuple[Union[TagSelector, DescendantSelector], dict[str, str]]):
    selector, body = rule
    return selector.priority

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
    def __init__(self, node: Element):
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
    def __init__(self, node: Union[Element, Text], parent, previous):
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
        self.parent: Union[DocumentLayout, BlockLayout] = parent
        self.previous: Union[BlockLayout, None] = previous
        """１つ前の（兄弟の）レイアウトオブジェクト"""
        self.children: list[Union[BlockLayout, LineLayout]] = []
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
            self.new_line() # 最初の1行目（空のLineLayout）を準備
            self.recurse(self.node)

        # note: width と height の計算順
        #   width: 親ブロックの幅が「あらかじめ」計算されている必要がある．＝ layout() の再帰呼び出しの「前」に計算する必要がある．
        #   height: 子ブロックの高さが「あらかじめ」計算されている必要がある．＝ layout() の再帰呼び出しの「後」に計算する必要がある．
        for child in self.children:
            child.layout()

        # 全ての子を含むのに十分な高さが必要．
        self.height = sum([child.height for child in self.children])

    def recurse(self, node: Union[Text, Element]):
        """
        インライン要素を再帰的にレイアウトする（ディスプレイリストを構築する）．
        """
        if isinstance(node, Text):
            for word in node.text.split():
                self.word(node, word)
        else:
            for child in node.children:
                self.recurse(child)

    def new_line(self):
        """
        改行処理
        """
        self.cursor_x = 0
        last_line = self.children[-1] if self.children else None
        new_line = LineLayout(self.node, self, last_line)
        self.children.append(new_line)

    def word(self, node: Text, word):
        """
        個々の単語をレイアウトオブジェクトとしてレイアウトツリーに組み込む．
        """
        weight = node.style["font-weight"]
        style = node.style["font-style"]
        if style == "normal": style = "roman" # CSS の normal を Tk の roman に変換
        size = int(float(node.style["font-size"][:-2]) * .75) # CSS のピクセルを Tk のポイントに変換
        font = get_font(size, weight, style)
        w = font.measure(word) # 英語は単語ごとにサイズが異なるので，都度幅を計算する．

        if self.cursor_x + w > self.width:
            # 折り返し
            self.new_line()

        # その行（LineLayout）に単語（TextLayout）を追加
        line = self.children[-1]
        previous_word = line.children[-1] if line.children else None
        text = TextLayout(node, word, line, previous_word)
        line.children.append(text)

        # x カーソルを次の単語まで移動
        self.cursor_x += w + font.measure(" ")

    def paint(self):
        """
        レイアウトオブジェクトからディスプレイリストに格納する描画命令を構築する．
        """
        cmds = []

        # コード例に使用される pre タグの背景をグレーにする．
        # warning: テキストは背景の上に描画される必要があるので，DrawText より DrawRect が前に来る必要がある．
        if isinstance(self.node, Element) and self.node.tag == "pre":
            x2, y2 = self.x + self.width, self.y + self.height
            rect = DrawRect(self.x, self.y, x2, y2, "gray")
            cmds.append(rect)

        bgcolor = self.node.style.get("background-color", "transparent")

        if bgcolor != "transparent":
            x2, y2 = self.x + self.width, self.y + self.height
            rect = DrawRect(self.x, self.y, x2, y2, bgcolor)
            cmds.append(rect)

        return cmds

class LineLayout:
    """
    1行を意味するレイアウトオブジェクト．
    BlockLayout の子となる．
    """
    def __init__(self, node, parent, previous):
        self.node = node
        self.parent: BlockLayout = parent
        self.previous: Union[LineLayout, None] = previous
        self.children: list[TextLayout] = []

    def layout(self):
        self.width = self.parent.width
        self.x = self.parent.x

        if self.previous:
            self.y = self.previous.y + self.previous.height
        else:
            self.y = self.parent.y

        for word in self.children:
            word.layout()

        # ベースラインに沿って単語を整列させる（テキストのサイズが異なるとバラバラになってしまうため）
        max_ascent = max([word.font.metrics("ascent") for word in self.children]) # 行内のテキストの最大アセント（高さ）
        baseline = self.y + 1.25 * max_ascent
        for word in self.children:
            # note: TextLayout の y はその行のレイアウトが完了した後にしか計算できないので，後から追加している．
            word.y = baseline - word.font.metrics("ascent")
        max_descent = max([word.font.metrics("descent") for word in self.children]) # 行内のテキストの最大ディセント（g や y などの文字の下側のはみ出し部分の深さ）

        self.height = 1.25 * (max_ascent + max_descent)

    def paint(self):
        return []

class TextLayout:
    """
    1単語を意味するレイアウトオブジェクト．
    LineLayout の子となる．
    """
    def __init__(self, node: Text, word, parent, previous):
        self.node = node
        self.word = word
        self.parent: LineLayout = parent
        self.previous: Union[TextLayout, None] = previous
        self.children = []

    def layout(self):
        weight = self.node.style["font-weight"]
        style = self.node.style["font-style"]
        if style == "normal": style = "roman" # CSS の normal を Tk の roman に変換
        size = int(float(self.node.style["font-size"][:-2]) * .75) # CSS のピクセルを Tk のポイントに変換
        self.font = get_font(size, weight, style)

        self.width = self.font.measure(self.word)
        if self.previous:
            space = self.previous.font.measure(" ") # 1つ前の単語に適用されているフォント基準でスペース幅を計算
            self.x = self.previous.x + space + self.previous.width
        else:
            self.x = self.parent.x

        self.height = self.font.metrics("linespace")

    def paint(self):
        color = self.node.style["color"]
        return [DrawText(self.x, self.y, self.word, self.font, color)]

class DrawText:
    """
    テキストを描画するためのコマンド
    """

    def __init__(self, x1, y1, text, font: tkinter.font.Font, color):
        self.top = y1
        self.left = x1
        self.text = text
        self.font = font
        self.bottom = y1 + font.metrics("linespace")
        self.color = color

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
            anchor='nw',
            fill=self.color
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
            height=HEIGHT,
            bg="white"
        )
        self.canvas.pack()
        self.scroll = 0
        """画面座標(y)の一番上がページ座標(y)のどこに位置するのかを表すオフセット値"""
        self.url = None

        # イベントハンドラのバインド処理
        self.window.bind("<Down>", self.scrolldown) # <Down>: 下矢印キーのクリック
        self.window.bind("<Up>", self.scrollup) # <Up>: 上矢印キーのクリック
        self.window.bind("<Button-1>", self.click) # <Up>: マウスの左ボタンのクリック

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
        self.url = url
        body = url.request()
        self.nodes = HTMLParser(body).parse()

        rules = DEFAULT_STYLE_SHEET.copy()

        links = [
            node.attributes["href"] for node in tree_to_list(self.nodes, [])
                if isinstance(node, Element)
                    and node.tag == "link"
                    and node.attributes.get("rel") == "stylesheet"
                    and "href" in node.attributes
        ]
        for link in links:
            style_url = url.resolve(link)
            try:
                body = style_url.request()
            except:
                # ダウンロードに失敗したスタイルシートは単に無視する．
                continue
            rules.extend(CSSParser(body).parse())

        style(
            self.nodes,
            sorted(rules, key=cascade_priority)
        )

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

    def scrollup(self, e):
        """
        note:
            最上部を過ぎて（マイナス方向へ）スクロールはできない．
        """
        # 現在のスクロール位置から SCROLL_STEP を引き、0未満にはならないようにする
        self.scroll = max(self.scroll - SCROLL_STEP, 0)
        self.draw() # 再描画

    def click(self, e: tkinter.Event):
        x, y = e.x, e.y # クリックした位置
        y += self.scroll

        # note: ここで取得される obj は普通１つだが，負のマージンなどによって複数が含まれる場合があるので配列形式．
        objs = [
            obj
            for obj in tree_to_list(self.document, [])
                if obj.x <= x < obj.x + obj.width
                    and obj.y <= y < obj.y + obj.height
        ]
        if not objs: return
        elt = objs[-1].node # クリックされた要素の中で一番手前に描画されている（= 一番最後にパースされている）要素

        while elt:
            if isinstance(elt, Text):
                pass
            elif elt.tag == "a" and "href" in elt.attributes:
                url = self.url.resolve(elt.attributes["href"])
                return self.load(url)
            elt = elt.parent

if __name__ == "__main__":
    import sys
    Browser().load(URL(sys.argv[1]))
    tkinter.mainloop()
