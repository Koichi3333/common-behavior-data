<div align="center">

# Common Behavior Data

**Behavior should be portable.**

行動データを、シミュレータ・ロボット・モデル・ツールをまたいで
**再利用可能な資産**に変えるためのオープンなフレームワークです。

[![Status: experimental](https://img.shields.io/badge/status-experimental-orange)](docs/limitations.md)
[![License: Apache 2.0](https://img.shields.io/badge/license-Apache--2.0-blue)](LICENSE)
[![Targets: 4](https://img.shields.io/badge/adapters-4%20targets-brightgreen)](adapters/README.md)

[![資料を読む](https://img.shields.io/badge/Technical%20Concept%20Deck-PDF-EC1C24?style=for-the-badge&logo=adobeacrobatreader&logoColor=white)](docs/media/technical-concept-deck.pdf)

[English README](README.md) ·
**[Showcase](showcase/)** ·
[コンセプト](docs/concept.md) ·
[仕様](specification/README.md) ·
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

理由付きの全リスト: [`docs/limitations.md`](docs/limitations.md)

## ライセンスと第三者素材

本リポジトリのオリジナルのソースコードとドキュメントは、特記なき限り
**Apache-2.0**（[`LICENSE`](LICENSE)）です。

データセット、モデル重み、デモ用メディア、ソース動画、VRM アセット、ロボット
アセット、その他の第三者素材は別のライセンス条件を持つ場合があります
（`examples/*/sample_output/` のサンプル出力を含む）。再配布の前に
[`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md) をご確認ください。
