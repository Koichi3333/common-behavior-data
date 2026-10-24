<div align="center">

# Common Behavior Data

**Behavior should be portable — and should say where it isn't.**

行動データを、シミュレータ・ロボット・モデル・ツールをまたいで
**再利用可能な資産**に変えるためのオープンなフレームワークです。
そして、**どこで壊れたかをデータ自身が申告できる**ようにするための試みです。

[![Status: experimental](https://img.shields.io/badge/status-experimental-orange)](docs/limitations.md)
[![License: Apache 2.0](https://img.shields.io/badge/license-Apache--2.0-blue)](LICENSE)
[![Targets: 4](https://img.shields.io/badge/adapters-4%20targets-brightgreen)](adapters/README.md)

[![資料を読む](https://img.shields.io/badge/Technical%20Concept%20Deck-PDF-EC1C24?style=for-the-badge&logo=adobeacrobatreader&logoColor=white)](docs/media/technical-concept-deck.pdf)

[English README](README.md) ·
**[Showcase](showcase/)** ·
[コンセプト](docs/concept.md) ·
[仕様](specification/README.md) ·
[壊れた箇所](docs/compatibility_findings.md) ·
[限界](docs/limitations.md)

<img src="docs/media/comparison.gif" width="760" alt="1つの行動データセットを MediaPipe オーバーレイ・MuJoCo ヒューマノイド・Isaac Sim の Unitree G1・Unity VRM アバターで同一タイムライン上に再生">

*1本のソース動画 → 1つの行動データセット → 同一タイムライン上の4つの異なるターゲット*

</div>

---

> **このページは日本語での概要です。**
> 正となるドキュメントは [English README](README.md) です。このドキュメントには
> 「何を、なぜ作っているか」を日本語で記載しています。

---

## CBDとは何か

行動をデジタル活用する場合は、通常、**特定のツールの中へ**取り込まれます　ー　モーションキャプチャ形式、
ゲームエンジンのクリップ、シミュレータの軌道、データセットスキーマ、あるロボットの
関節構成などです。ツールが変われば、パイプラインを作り直す必要が生じ、モデルのアップデートによるやり直しも多く発生します。

CBD は、その中間に再利用可能な層を1つ置き、**観測そのものを資産に変えるものです**。

```text
映像 / 画面録画 / センサー / その他の観測
        ↓
   行動抽出                     ← 差し替え可能
        ↓
   Canonical CBD                ← 資産
        ↓
   ターゲットごとの Adapter      ← 差し替え可能
        ↓
   MuJoCo · Unity · Isaac Sim · ロボット · ML データセット
```

データソースとして映像を最も重視しています。理由は、**最も精度が高いから**ではなく、**誰でも作成出来るから**です。
センサーは映像の対極にあるわけではなく、映像が苦手な部分——キャリブレーション、スケール、
Ground Truth、そして接触・力・トルクのように映像がまったく見られない量——を補うものとして利用していく予定です。

CBD は **人体モーション専用ではありません。** 現在のパイプラインが扱うのは人体
モーションですが、*観測 → 行動 → 再利用* という構造自体は、例えば視界の情報やPC作業画面のスクリーンキャプチャなど様々なものに応用可能であると考えています。
詳細: [`docs/behavior_asset.md`](docs/behavior_asset.md)

現在の Adapter は MediaPipe オーバーレイ・MuJoCo・Unity/VRM・Isaac Sim（Unitree G1）の4つで、
互いにコードを共有していません。共通しているのは行動データセットだけです。
実際に動いた結果と、そこで**何が機能しなかったか**は [`showcase/`](showcase/) にあります。

---

## いま取り組んでいる中心の問題

行動データは、**派手に壊れません。静かに壊れます。**

ファイルは読み込めます。全フィールドが構文的に正しく、Adapter は最後まで走り、
シミュレータは問題なく再生します。そしてその中で、19本の骨のうち4本
（`chest`・`neck`・両 `shoulder`）は、全96フレームで一度も回転していません。
**体幹が静止していたからではなく、観測できていなかったから**です。
そして、そのことをファイルは何も語りません。

これは仮定の話ではなく、このリポジトリが公開しているサンプルそのものです。
pick-and-place のクリップなのに `phase` は全96フレームが `Idle`、
`interaction_events.csv` は見出し行だけ、物体の3D位置を持つエントリは173件中1件で、
その1件は `[NaN, NaN, 0.3]` ——にもかかわらず `quality.json` は
`object_coverage: 1.0` と報告します。

どれも同じ故障です：**消費者が「測った値」と区別できない値**。
パースエラーでも欠損でもなく、出どころの印がない自信ありげな数字です。

### 2種類のギャップ

このプロジェクトで分かったことは、すべて次の2つのどちらかに分類されます。
**どちらなのかで、できることが決まります。**

```text
data gap（データのギャップ）   記録がそれを持っていない
                               → 上流で閉じられる：生成器の改善・センサー・
                                 スキーマへのチャネル追加

body gap（身体のギャップ）     2つの身体が本当に食い違っている
                               → 閉じられない：測って、移植先の単位で
                                 数字として公開するしかない
```

data gap は誰かのバグです。body gap は「脊椎を持たない 1.32m のロボット」という
事実で、動きは**コピーではなく解く**しかなく（方向残差 平均 **6.87°**）、家具の方を
ロボットに合わせて縮める（`scale = 0.685`）しかなく、着座クリップではリターゲット段で足首ピッチが
全96フレーム限界に張り付きます。ロボットを伸ばせば、それはハードウェアについての捏造です。

そして2つはつながっています。**data gap は、身体が変わった瞬間に body gap として
現れます。** 回転を持たない4本の骨はデータセットの中では欠けたフィールドですが、
G1 の上では「画像がグラスを置く位置」と「ロボットの手が行く位置」の **0.296 m** の
食い違いとして現れます。詳細: [`docs/concept.md`](docs/concept.md#the-problem)

この問題の大きさは、G1 Adapter が自分の出力を「その量がどこから来たか」で
採点したときに数字になりました
（[`adapter_report.json`](examples/human-capture/sample_output/07_groot_g1_v2/adapter_report.json)）：

```text
stage_provenance.ratio
  measured     0.0000     ← Canonical CBD が持っていた
  derived      0.9984     ← Adapter が自前で解いた幾何
  synthesized  0.0016
```

ロボットの動きのうち、Canonical CBD が「測れた」と言える量に支えられている部分は
**ゼロ**でした。Adapter は誠実にこれを公開しましたが、**表現の側には伝える手段が無い**。

そこで CBD は今、次の2つを順番に進めています。

1. **データの中の出どころ（provenance）** ——**生成器側は実装済み（データ版 `0.3.0`）**。
   `position_source` が1フィールドだけで実現していた原則を、全チャネルの規則へ一般化しました。
   各チャネルが `measured` / `derived` / `estimated` / `prior` /
   `degenerate`（＝書かれているが情報を持たない）/ `absent`（＝存在しない）のいずれかを申告し、
   **判定は決め打ちではなく系列を測って**行います。エピソード単位では
   `episode_kind`（観測か生成か）と出どころの条件（再配布可否・帰属）も書き出します。
   **ただし読む側はまだ誰もいません** —— アダプタは未対応、検証ツールも無し。
   依存するものが無い申告は、契約ではなく主張です
2. **実体（embodiment）が変わっても行動の意図が生き残るか。** G1 で半分は答えが出ました
   ——運動学としては載る、ただしポリシーは未実行

経緯と理由: [`docs/concept.md`](docs/concept.md) ·
壊れた箇所の台帳: [`docs/compatibility_findings.md`](docs/compatibility_findings.md) ·
次の一手: [`docs/roadmap.md`](docs/roadmap.md)

---

## はじめての方へ

| やりたいこと | 行き先 |
|---|---|
| **何ができるか見る** | [`showcase/`](showcase/) — 出力の映像をまず確認できます |
| **ミニマムのサンプルを動かす** | [`examples/`](examples/) — Colab ノートブック2本 |
| **現行パイプラインを動かす** | [`generators/`](generators/) → [`adapters/`](adapters/) |
| **データ形式を読む** | [`specification/`](specification/README.md) |
| **全体像を読む** | [English README](README.md) |

---

## 共同開発への参加

**Contribution Welcomeです。** 特に、別のシミュレータ / エンジン /
ロボット向けの **Adapter を追加する**こと、**新しい Generator を作る**こと、
そして**既存の CBD を新しい実体で試し、どういったところが機能しなかったかを報告いただける**と助かります。

> **行動をひとつ選ぶ → 新しい場所で動かす → 新しい発見を教えてください。**

詳細は [`CONTRIBUTING.md`](CONTRIBUTING.md) をご覧ください。大きな設計変更の前には
Issue か Discussion で提起をいただければ幸いです。

**CBD を利用される方へ。** 接続したいロボット・シミュレータ・モデル・
アプリケーションはありますか？ まだ存在しない Adapter が必要でしょうか？
[Discussion](https://github.com/Koichi3333/common-behavior-data/discussions) か
[Issue](https://github.com/Koichi3333/common-behavior-data/issues) を開いてください。

---

## 限界

このリポジトリは**実験段階**です。単一人物・単眼推定のキャプチャであり、MuJoCo 再生は
Kinematic replay、G1 Adapter は**ポリシーを実行していません**。Sim-to-real の主張も、
ロボットのタスク成功の主張もありません。スキーマは随時、変更されます。

`0.3.0` から、データは自分のどのチャネルが実測だったかを申告します。ただし
**申告しても欠落は埋まりません** —— 4本の骨と `phase` は「書かれているのに情報を持たない」
状態のままで、`degenerate` という印が付いただけです。読む側のアダプタもまだありません。
また、**同梱のサンプル出力は `0.2.0`** で、これらのフィールドを含みません。

理由付きの全リスト: [`docs/limitations.md`](docs/limitations.md)

## ライセンスと第三者素材

本リポジトリのオリジナルのソースコードとドキュメントは、特記なき限り
**Apache-2.0**（[`LICENSE`](LICENSE)）です。

データセット、モデル重み、デモ用メディア、ソース動画、VRM アセット、ロボット
アセット、その他の第三者素材は別のライセンス条件を持つ場合があります
（`examples/*/sample_output/` のサンプル出力を含む）。再配布の前に
[`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md) をご確認ください。
