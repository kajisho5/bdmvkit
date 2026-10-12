<p><img src="docs/images/logo/lockup-dark.svg" alt="bdmvkit" height="56"></p>

# bdmvkit

**Python だけで Blu-ray（BDMV）をオーサリングするライブラリです。** Blu-ray プレーヤーがディスクを操作するときに読むファイルを書き出します。

* チャプターマーク付きのプレイリスト（`.mpls`）
* プレーヤーがシーク（再生位置の移動）に使う位置表付きのクリップ情報（`.clpi`）
* HDMV のナビゲーション命令を入れた `index.bdmv` と `MovieObject.bdmv`
* メニュー：ボタン、ボタン間の矢印キーの移動先、ボタンが実行する命令を入れた Interactive Graphics ストリーム
* PGS 字幕ストリーム（`.sup`）

ffmpeg と x264 を使い、Blu-ray 向けの設定でクリップをエンコードする機能もあります。標準ライブラリ以外に依存せず、ffmpeg が必要なのはエンコードのときだけです。

**状態：0.7。** チャプター・音声・字幕付きのタイトル、プレイリスト（順番・ランダム・シャッフル）と全再生、ボタンでタイトル・チャプター・プレイリスト・別のメニューへ移ったり音声と字幕を切り替えたり、選ぶボタンを指定してメニューを開いたりするメニューを作れます。ループ回数、終了時の移動先の上書き、リンクのトランジション、タイトルごとに使えなくするリモコンキー、720p にも対応します。このナビゲーションは [oncemore](https://github.com/kajisho5/oncemore) が書くものとバイト単位で同じです。0.4 で再生中のタイトルに重ねるポップアップメニューに、0.5 で動きや音楽のあるメニューに、0.6 で 720p メニューのボタンストリームに、0.7 で DTS-HD の音声トラックに対応しました。

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

1 つのクリップに複数の音声トラックを入れられます。映像ファイル自身の音声でも別のファイルでもよく、k 番目のトラックがタイトルの k 番目の音声トラックになります（音声の無いファイルは無音、映像より短い音声は無音で埋めます）。

```python
from bdmvkit.encode import AudioTrack

encode_clip("feature.mov", "feature.m2ts", audio=[
    AudioTrack(),                                   # 映像ファイル自身の音声、AC-3
    AudioTrack("commentary.wav", "lpcm"),           # 別のファイル、LPCM
    AudioTrack("feature.mov", "ac3", 6, stream=1),  # 2 本目の音声ストリーム、5.1ch
])
disc.add_title("feature.m2ts", audio=[("ac3", 2, "en"), ("lpcm", 2, "en"), ("ac3", 6, "ja")])
```

`Disc.write` は、タイトルが宣言したトラックがすべてクリップにあるかを確かめます。

拡張ごとコピーした DTS は、その種類どおりに `"dtshd"`（DTS-HD High Resolution Audio）または `"dtshd_ma"`（DTS-HD Master Audio）と宣言し、48 kHz を超えるときはサンプリングレートも書きます（`("dtshd_ma", 8, "en", 96000)`。LPCM も 96・192 kHz にできます）。ffmpeg はクリップ内の DTS を拡張ではなくチャンネル数で区別して書くため、`Disc.write` がディスクに置くコピーの DTS トラックを、タイトルの宣言どおりの種類に書き換えます。

```python
encode_clip("feature.mkv", "feature.m2ts", audio=[AudioTrack("feature.mkv", "copy", 8)])
disc.add_title("feature.m2ts", audio=[("dtshd_ma", 8, "en")])
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

ボタンの `action`、タイトルの `end`（再生が終わったときの移動先）、ディスクの最初の再生は「アクション」で書きます：`title:<n>`、`chapter:<n>:<c>`、`playlist:<id>`、`playall`、`menu:<id>`（`menu:<id>:<button>` でそのボタンを選んだ状態）、`lastmenu`、`resume`、`audio:<n>`、`subtitle:<n>` または `subtitle:off`、`stop`。矢印キーは、ボタンの `nav`（`{"down": "scene2"}`）で指定しない限り、その方向でいちばん近いボタンへ移ります。ボタンのストリームだけを作る `bdmvkit.igs` は、ほかのツールからも使えます。`igs.ig_stream(buttons, frame_rate, size=(1280, 720))` で 720p のメニューにボタンを置けます。

```python
disc = Disc(title_key="menu:main")
a = disc.add_title("feature.m2ts", chapters=[0, 300], audio=[("ac3", 6, "en"), ("ac3", 6, "ja")],
                   subtitles=["en", "ja"], default_subtitle=1, end="lastmenu")
n = disc.add_title("notice.m2ts", prohibit=["next", "fast_forward", "menu"], end="title:1")
disc.add_playlist("both", [n, (a, 2, None)], order="shuffle", end="menu:main")
disc.add_menu("main", "menu.png", [
    MenuButton("play", 160, 700, "play.png", action="title:2"),          # 先に注意書き
    MenuButton("ja", 160, 800, "ja.png", action="title:1", audio=2, subtitle=0),
    MenuButton("both", 160, 900, "both.png", action="playlist:both"),
], loop=3, end="playall", seconds=10)
```

メニューの背景には動画も使え、BGM も付けられます。そのようなメニューは最後まで再生するとまた再生し、2 回目からは `loop_point`（秒）から再生します。長さは `seconds` で指定しない限り、動画の長さ、動画が無ければ BGM の長さです。

```python
disc.add_menu("main", "loop.mp4", buttons, music="theme.wav", loop_point=2.0)
```

タイトルにはポップアップメニューを付けられます。再生中の映像の上に出るボタンで、リモコンのポップアップメニューキーで開きます。ボタンの画像はメニューと同じく 1920 × 1080 の画面上に置きます。音声や字幕を切り替えるだけのボタンは、押すとメニューを閉じます。

```python
disc.add_popup(a, [
    MenuButton("scenes", 160, 900, "scenes.png", "scenes-on.png", "scenes-off.png",
               action="menu:main"),
    MenuButton("ja", 560, 900, "ja.png", normal="ja-off.png", action="audio:2"),
])
```

その下の層として、`bdmvkit.program` がエンコード済みのクリップ（タイトル、プレイリスト、ボタン入りのメニュークリップ、トランジション）でできたディスクを表し、`bdmvkit.nav.write_program` がそれを書き出します。`nav.Navigation` はメニューのボタンが実行する命令を返すので、IG ストリームを自分で作るツールからも使えます。

```sh
bdmvkit encode feature.mov feature.m2ts --chapters 0,300,600
bdmvkit build disc.json out
```

ディスクの作りは次のとおりです。

* フレームレートは 23.976（1080p）、25、29.97 です。25 と 29.97 は、規格に合わせて 1080i のストリームにプログレッシブのフレームとして入れます。program は 720p（23.976、50、59.94。25 と 29.97 は倍のレートで入れます）にもできます。`encode_clip` が作るのは 1080 のクリップです。
* 音声は AC-3、LPCM、DTS、DTS-HD High Resolution Audio、DTS-HD Master Audio です（48 kHz を超える DTS-HD トラックは、48 kHz のコアの上のものとして記録します）。
* 字幕はクリップに多重化した PGS ストリームです。`pgs.write_sup` で画像から作り、`encode_clip(..., sups=[...])` で入れます。
* ディスクを入れたときとトップメニューキーを押したときは、最初のメニューを開きます（メニューが無ければタイトル 1 を再生。`Disc(first_play=..., title_key=...)` で指定できます）。
* タイトル、プレイリスト、全再生、メニューがこの順に Blu-ray のタイトルになります。ランダムとシャッフルのプレイリストは、項目ごとのプレイリストファイルを、プレーヤーの乱数命令で選んで再生します。汎用レジスタ 1〜8 には、最後に表示したメニュー、リンクで選ぶボタン、メニューのループ回数、終了時の移動先の上書き、ストリームの選択、ランダム再生の状態を入れます（`nav.py`）。
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
* メニューのボタンをリモコンのキーで選んで決定し、タイトル・チャプター・プレイリスト・別のメニューへ移ること、シャッフルしたプレイリストが各項目を 1 回ずつ再生すること、ループ回数のあるメニューが自動で次へ進むこと
* 動画と BGM のメニューがループ位置から再生し直すこと、ループ回数のあるメニューがその回数だけ再生して自動で次へ進むこと
* 再生中のタイトルでポップアップメニューキーを押すとポップアップメニューが開き、そのボタンで別のタイトルやチャプターへ移ること
* あらゆる種類のアクション・タイトル・プレイリスト・メニューが、どの命令になるか

ファイルのうち内容が決まっているバイトも確かめています。

## 支援する

bdmvkit は無料で、これからも無料です。役に立ったら [GitHub Sponsors](https://github.com/sponsors/kajisho5)（このリポジトリ上部の **Sponsor** ボタン）から開発を支援できます。不具合の報告も同じくらい助かります：[Issues](https://github.com/kajisho5/bdmvkit/issues)。

ロゴ・色・文章の決まりは [docs/DESIGN.md](docs/DESIGN.md)（英語）にあります。

## ライセンス

GNU Lesser General Public License バージョン 3 以降（[COPYING.LESSER](COPYING.LESSER) と [COPYING](COPYING) を参照）。bdmvkit はどのライセンスのプログラムからも使えますが、bdmvkit 自体を変更した部分は LGPL のままです。
