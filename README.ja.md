<p><img src="docs/images/logo/lockup-dark.svg" alt="bdmvkit" height="56"></p>

# bdmvkit

**Python だけで Blu-ray（BDMV）をオーサリングするライブラリです。** Blu-ray プレーヤーがディスクを操作するときに読むファイルを書き出します。

* チャプターマーク付きのプレイリスト（`.mpls`）
* プレーヤーがシーク（再生位置の移動）に使う位置表付きのクリップ情報（`.clpi`）
* HDMV のナビゲーション命令を入れた `index.bdmv` と `MovieObject.bdmv`
* メニュー：ボタン、ボタン間の矢印キーの移動先、ボタンが実行する命令を入れた Interactive Graphics ストリーム
* PGS 字幕ストリーム（`.sup`）

ffmpeg と x264 を使い、Blu-ray 向けの設定でクリップをエンコードする機能もあります。標準ライブラリ以外に依存せず、ffmpeg が必要なのはエンコードのときだけです。

**状態：0.2。** チャプター・音声・字幕付きのタイトルと、ボタンでタイトル・チャプター・別のメニューへ移るメニューを作れます。次はポップアップメニュー（再生中のタイトルの上に出るメニュー）と、動きや音楽のあるメニューです。これらは元になった [oncemore](https://github.com/kajisho5/oncemore) ではすでに動いています。

## なぜ作ったか

オープンソースの Blu-ray ツール（tsMuxer など）は、映像や音声を BDMV フォルダにまとめるところまでで、その上のナビゲーションの層は作りません。ナビゲーションの層とは、メニュー、ムービーオブジェクト、プレイリストと命令のことです。

bdmvkit はこの層を自前で書き、作ったディスクをすべて libbluray で再生して確かめています。

## インストール

```sh
pip install bdmvkit
```

リリースはバージョン番号で決まります。`pyproject.toml`（と `bdmvkit/__init__.py`）のバージョンがまだタグの無い番号で `main` に入ると、`.github/workflows/release.yml` がテスト・ビルド・タグ付きの GitHub リリース・PyPI 公開（trusted publishing、環境 `pypi`）まで行います。バージョンを上げた PR をマージするだけで済みます。

## 使い方

```python
from bdmvkit import Disc
from bdmvkit.encode import encode_clip

encode_clip("feature.mov", "feature.m2ts", chapters=[0, 300, 600])   # チャプター位置をキーフレームに
encode_clip("extras.mp4", "extras.m2ts", fps=(25, 1))

disc = Disc()
disc.add_title("feature.m2ts", chapters=[0, 300, 600], audio=[("ac3", 2, "ja")])
disc.add_title("extras.m2ts", fps=(25, 1))
disc.write("out")                       # out/BDMV/...
```

メニューは 1 枚の画像とボタンでできています。ボタンは、選択されたときの見た目の画像（指定すれば決定したとき・選択される前の画像も）を 1920 × 1080 のメニュー上の位置に置き、リンク先を付けます。

```python
from bdmvkit import Disc, MenuButton

disc = Disc()
disc.add_title("feature.m2ts", chapters=[0, 300, 600], end="menu:main")
disc.add_menu("main", "menu.png", [
    MenuButton("play", 160, 700, "play-lit.png", "play-on.png", action="title:1"),
    MenuButton("scene2", 160, 800, "scene2-lit.png", action="chapter:1:2"),
])
disc.write("out")
```

リンク先は `title:<n>`、`chapter:<n>:<c>`、`menu:<id>` です。タイトルの `end`（再生が終わったときの移動先）も同じ書き方です。矢印キーは、ボタンの `nav`（`{"down": "scene2"}`）で指定しない限り、その方向でいちばん近いボタンへ移ります。ボタンのストリームだけを作る `bdmvkit.igs` は、ほかのツールからも使えます。

```sh
bdmvkit encode feature.mov feature.m2ts --chapters 0,300,600
bdmvkit build disc.json out
```

ディスクの作りは次のとおりです。

* フレームレートは 23.976（1080p）、25、29.97 です。25 と 29.97 は、規格に合わせて 1080i のストリームにプログレッシブのフレームとして入れます。
* 音声は AC-3、LPCM、DTS です。
* 字幕はクリップに多重化した PGS ストリームです。`pgs.write_sup` で画像から作り、`encode_clip(..., sups=[...])` で入れます。
* ディスクを入れたときとトップメニューキーを押したときは、最初のメニューを開きます（メニューが無ければタイトル 1 を再生）。
* メニューはタイトルの後に並ぶインタラクティブなタイトルです。画像を静止画として表示し、ボタンはそのクリップに入れた Interactive Graphics ストリームです。メニューはディスクを書き出すときにエンコードします（ffmpeg）。

フォルダからディスクイメージを作るには [udfkit](https://github.com/kajisho5/udfkit)（UDF 2.50）を使ってください：`udfkit bluray out disc.iso --label MY_DISC`。

## テスト

```sh
python -m unittest discover -s tests -t .
```

テストでは、本物のクリップをエンコードしてディスクを書き出し、VLC・mpv・Kodi が Blu-ray の再生に使う **libbluray** で読み戻します。確かめている内容は次のとおりです。

* タイトルとその長さ
* チャプターの位置
* 映像・音声・字幕のストリームと言語
* ディスクを入れたところから再生して、タイトルとチャプターを順にたどれること
* メニューのボタンをリモコンのキーで選んで決定し、タイトル・チャプター・別のメニューへ移ること

ファイルのうち内容が決まっているバイトも確かめています。

## 支援する

bdmvkit は無料で、これからも無料です。役に立ったら [GitHub Sponsors](https://github.com/sponsors/kajisho5)（このリポジトリ上部の **Sponsor** ボタン）から開発を支援できます。不具合の報告も同じくらい助かります：[Issues](https://github.com/kajisho5/bdmvkit/issues)。

ロゴ・色・文章の決まりは [docs/DESIGN.md](docs/DESIGN.md)（英語）にあります。

## ライセンス

GNU Lesser General Public License バージョン 3 以降（[COPYING.LESSER](COPYING.LESSER) と [COPYING](COPYING) を参照）。bdmvkit はどのライセンスのプログラムからも使えますが、bdmvkit 自体を変更した部分は LGPL のままです。
