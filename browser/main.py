import socket

class URL:
    def __init__(self, url):
        # URL のパース．
        self.scheme, url = url.split("://", 1)
        assert self.scheme == "http"

        if "/" not in url:
            url = url + "/"

        self.host, url = url.split("/", 1)
        self.path = "/" + url

    def request(self):
        # ソケットの作成．
        s = socket.socket(
            family=socket.AF_INET, # アドレスファミリー（＝ 他のコンピュータを見つける方法）．INET（＝ IPv4 を使用）．
            type=socket.SOCK_STREAM, # ソケットタイプ（＝ 行われる会話の種類）．STREAM（＝ 任意の量のデータを送信できる）．
            proto=socket.IPPROTO_TCP, # プロトコル（＝ 2台のコンピュータが接続を確立する方法）．
        )
        s.connect((self.host, 80))

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
