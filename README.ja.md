# bdmvkit

**Python だけで Blu-ray（BDMV）をオーサリングするライブラリです。** Blu-ray プレーヤーがディスクを操作するときに読むファイルを書き出します。

* チャプターマーク付きのプレイリスト（`.mpls`）
* プレーヤーがシーク（再生位置の移動）に使う位置表付きのクリップ情報（`.clpi`）
* HDMV のナビゲーション命令を入れた `index.bdmv` と `MovieObject.bdmv`
* PGS 字幕ストリーム（`.sup`）

ffmpeg と x264 を使い、Blu-ray 向けの設定でクリップをエンコードする機能もあります。標準ライブラリ以外に依存せず、ffmpeg が必要なのはエンコードのときだけです。

**状態：0.1。** チャプター・音声・字幕付きのタイトルを順に再生するディスクを作れます。次は HDMV メニュー（Interactive Graphics：ボタン、ポップアップメニュー）を入れます。メニューは元になった [oncemore](https://github.com/kajisho5/oncemore) ではすでに動いていて、こちらへ移している途中です。

## なぜ作ったか

オープンソースの Blu-ray ツール（tsMuxer など）は、映像や音声を BDMV フォルダにまとめるところまでで、その上のナビゲーションの層は作りません。ナビゲーションの層とは、メニュー、ムービーオブジェクト、プレイリストと命令のことです。

bdmvkit はこの層を自前で書き、作ったディスクをすべて libbluray で再生して確かめています。

## インストール

```sh
pip install git+https://github.com/kajisho5/bdmvkit
```

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

```sh
bdmvkit encode feature.mov feature.m2ts --chapters 0,300,600
bdmvkit build disc.json out
```

ディスクの作りは次のとおりです。

* フレームレートは 23.976（1080p）、25、29.97 です。25 と 29.97 は、規格に合わせて 1080i のストリームにプログレッシブのフレームとして入れます。
* 音声は AC-3、LPCM、DTS です。
* 字幕はクリップに多重化した PGS ストリームです。`pgs.write_sup` で画像から作り、`encode_clip(..., sups=[...])` で入れます。
* ディスクを入れたときと、トップメニューキーを押したときは、タイトル 1 から再生します。

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

ファイルのうち内容が決まっているバイトも確かめています。

## ライセンス

GNU Lesser General Public License バージョン 3 以降（[COPYING.LESSER](COPYING.LESSER) と [COPYING](COPYING) を参照）。bdmvkit はどのライセンスのプログラムからも使えますが、bdmvkit 自体を変更した部分は LGPL のままです。
