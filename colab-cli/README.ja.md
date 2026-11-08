# `colab-cli/` — このリポジトリのノートブックをターミナルから Colab で動かす

[English](README.md) · [運用ガイド](guide/field_guide.ja.md) ·
[Where things run](../docs/runtime_environments.md)

公式の [`google-colab-cli`](https://github.com/googlecolab/google-colab-cli) で
Google Colab をコマンドラインから操作するための一式。インストール、認証、API キーの受け渡し、
動作確認、そして「ブラウザが無いと何が変わるか」の実測メモをまとめてある。
**このディレクトリだけで完結しており、外のファイルには依存も変更もしない。**

リポジトリの方針は *Colab CLI で動くものは Colab CLI で*
（[理由](../docs/runtime_environments.md)）。そのための入口がここ。

**クラウド（GitHub Codespaces、SSH 先の Linux）でもローカル（macOS / Linux）でも、
同じ3コマンドで動く。** Windows は WSL 内で使う。

## クイックスタート

リポジトリのルートで:

```bash
colab-cli/setup.sh        # uv と google-colab-cli 0.7.5 を入れる（何度流してもよい）
colab-cli/auth.sh         # 認証。マシンごとに1回
colab-cli/smoke_test.sh   # CPU の VM を確保 → 実行 → ファイル回収 → 停止（約1分）
```

セットアップはこれで全部。必要なのは Google アカウントだけ（Workspace アカウントも可）で、
`gcloud` も GCP プロジェクトも独自の OAuth クライアントも要らない。
動作確認にもこのリポジトリのノートブックにも、Colab の無料枠で足りる。

## クラウドとローカルで違うところ

違いは3つだけで、1つ目はスクリプトが吸収する。

| | クラウド（Codespaces・SSH） | ローカル（macOS / Linux / WSL） |
|---|---|---|
| **認証** | `auth.sh` が `$BROWSER` 経由で**手元のブラウザ**に開く（Codespaces・VS Code Remote）。素の SSH では `ws/.auth/auth_url.txt` とリンク1つの `index.html` を書くか、`--serve 8765` + ポート転送で開く | `auth.sh` が既定のブラウザで開く |
| **API キー**（任意） | Codespaces の Secret: GitHub → Settings → Codespaces → Secrets の *Repository access* に**このリポジトリ**を追加し、Codespace を **Rebuild**。別リポジトリにだけ共有された Secret はここには届かない。届いたものは `python3 colab-cli/tools/colab_secrets.py --list` で確認 | `cp colab-cli/.env.example colab-cli/.env` して記入（gitignore 済み）。または `export` するだけ |
| **残るもの** | Codespace を Rebuild / 再作成すると `~/.local` と `~/.config` が消え、CLI もトークンも無くなる。`setup.sh` と `auth.sh` を流し直す | やり直し不要 |

どちらでも、認証そのものは CLI 自身のフロー（ブラウザで同意 → 表示されたコードを貼る）。
`auth.sh` があるのは、認可 URL が約700文字あり、ターミナルからコピーすると途中で切れて
*エラー 400: Missing required parameter: scope* になるため
（[詳細](guide/field_guide.ja.md#-最大の落とし穴-urlの切れ)）。
エージェントやスクリプト向けには2段階版がある: `auth.sh --url-only` → `auth.sh --code <コード>`。

## このリポジトリのノートブックを流す

作業は `colab-cli/ws/`（gitignore 済み）の中で行い、**ノートブックはコピーしてから**
`-f` に渡す。`colab exec -f X.ipynb` は `X_output.ipynb` を**入力ファイルの隣**に書くので、
`-f ../../generators/...` と渡すとソースツリーに生成物が落ちる。

本線は generator → アダプタを**同一セッションで続けて流す**こと。各アダプタは generator が
VM 上に展開したデータセットをそのまま読むので、再アップロードは要らない。
リポジトリ同梱のサンプル動画を CPU で通す例:

```bash
cd colab-cli/ws
R=../..
cp $R/generators/video_to_cbd/cbd_generator_video_to_cbd.ipynb \
   $R/adapters/mujoco/cbd_adapter_mujoco.ipynb .

colab new -s cbd                                         # GPU があれば --gpu T4
python3 ../tools/colab_secrets.py -s cbd GEMINI_API_KEY   # 任意。最初の exec より前に
colab upload -s cbd $R/examples/human-capture/sample_output/source/source_video.mp4 \
                    /content/source_video.mp4
colab exec   -s cbd -f cbd_generator_video_to_cbd.ipynb --timeout 1800 2>&1 | tee generator.log
colab exec   -s cbd -f cbd_adapter_mujoco.ipynb         --timeout 1800 2>&1 | tee mujoco.log
grep -nE "^(Traceback|[A-Za-z]*Error:)" *.log            # セルが失敗しても止まらないので確認
colab download -s cbd /content/human_behavior_demo_2_0/cbd_dataset.zip ./cbd_dataset.zip
colab stop -s cbd && colab sessions                      # 必ず。停止確認まで
```

自分の動画を使うときは同じ `/content/source_video.mp4` にアップロードする。
アダプタは最後に出力パスを表示するので、そのディレクトリを VM 上で zip にして、
停止前に `colab download` で取る。編集するのは元のノートブック。`ws/` のコピーは使い捨て。

### どのノートブックがヘッドレスで動くか

| ノートブック | CLI から | 補足 |
|---|---|---|
| [`generators/video_to_cbd/`](../generators/video_to_cbd/) | **そのまま動く** | ヘッドレスを検知してアップロードウィジェットを開かず、`/content/source_video.mp4` を読む。`GEMINI_API_KEY` は `os.environ` から読み、無ければキャプションと物体再分類の2セルだけスキップ |
| [`adapters/mediapipe_overlay/`](../adapters/mediapipe_overlay/)・[`mujoco/`](../adapters/mujoco/)・[`unity_vrm/`](../adapters/unity_vrm/) | **そのまま動く** | 同じくヘッドレス検知あり。同一セッションで generator が残したデータセットを読む（Unity での再生は手元のマシン） |
| [`examples/human-capture/human_behavior_demo_2_0.ipynb`](../examples/human-capture/) | **そのままでは不可** | `input()` ×2・`drive.mount()`・`userdata.get()` を含む。[レシピ](guide/field_guide.ja.md#対話コードinput-などの扱い)での差し替えと、セッションごとの Drive 同意が要る |
| [`examples/language-to-motion/human_behavior_vla_trainer.ipynb`](../examples/language-to-motion/) | 未確認 | `drive.mount()` を呼ぶ |
| [`adapters/isaac_sim_groot_g1/`](../adapters/isaac_sim_groot_g1/) | **Colab では不可** | リターゲット・finalize・compose はどのマシンでも動く素の Python。レンダと PhysX は RTX GPU の VM が必要（[理由](../docs/runtime_environments.md#the-one-exception-isaac-sim)） |

キーは `colab_secrets.py` で渡し、**`colab exec` に渡すコードには絶対に書かない**。
`colab exec` は実行したコードと出力の両方を
`~/.config/colab-cli/history/<session>.jsonl` に平文で追記する。
ノートブック自体は書き換えないので、ブラウザで開けば本物の Colab Secrets が使われる。

## 守ること5つ

1. **必ず `colab stop -s <name>`。** ターミナルを閉じても VM は解放されない。
   `colab sessions` で確認する。このリポジトリで Claude Code を使うと、応答が終わるたびに
   止め忘れたセッションがあれば警告が出る。Stop フックはリポジトリの `.claude/settings.json` に
   登録してあるので、設定は要らない。
2. **`--timeout` を必ず付ける。** 既定は30秒。無音時間ではなく総実行時間の締切で、
   ノートブックではセルごとに適用される。
3. **終了コードを信じない。** セルが失敗しても止まらず、`colab exec` は 0 で終わる。
   ログを `Traceback` で grep する。
4. **止める前に回収する。** `/content` はセッションと一緒に消え、`files.download()` は
   ブラウザが無いと黙って何もしない。`colab download` で取る（ファイルのみ。ディレクトリは VM 上で zip にする）。
5. **ブラウザが無い = ウィジェットが無い。** `input()`・`files.upload()`・`userdata.get()` は
   [運用ガイド](guide/field_guide.ja.md#対話コードinput-などの扱い)のレシピを使う。

## このディレクトリの中身

| パス | 内容 |
|---|---|
| [`setup.sh`](setup.sh) | `uv` と `google-colab-cli`（0.7.5 に固定。`COLAB_CLI_VERSION=latest` で変更可）を入れ、`ws/` を作り、Claude Code 用 skill を書き出す |
| [`auth.sh`](auth.sh) → [`tools/auth.py`](tools/auth.py) | URL をターミナルに通さない認証 |
| [`smoke_test.sh`](smoke_test.sh) | new → exec → download → stop。失敗しても必ず停止する。追加引数は `colab new` へ（例: `--gpu T4`） |
| [`tools/colab_secrets.py`](tools/colab_secrets.py) | キー（環境変数 → `.env` → Codespaces Secret の順）をセッションへ渡し、`userdata.get()` を使えるようにする |
| [`tools/ptyrun.py`](tools/ptyrun.py) | `colab drivemount` / `colab auth` を端末なしで完走させる |
| [`hooks/colab_session_guard.py`](hooks/colab_session_guard.py) | Claude Code の Stop フック（リポジトリの `.claude/settings.json` で全員に登録済み）。止め忘れたセッションを警告 |
| [`examples/drive/`](examples/drive/) | マウントした Drive 経由で `.py` から書き、`.ipynb` から読む例 |
| [`guide/field_guide.ja.md`](guide/field_guide.ja.md) · [英語版](guide/field_guide.md) | 実測に基づく挙動: 認証・ノートブック・秘密情報・成果物・Drive・トラブルシューティング |
| [`CLAUDE.md`](CLAUDE.md) | Claude Code がこのディレクトリで作業するときの運用ルール |
| [`.env.example`](.env.example) | ローカル用キーのひな形 |
| `ws/` | 作業ディレクトリ。`.gitkeep` 以外は git 管理外 |
| `.claude/skills/colab-operator/` | `setup.sh` が `colab skill` から生成（インストール済み CLI と常に一致。gitignore 済み） |

## 状態 — 何を動かし、何をまだ動かしていないか

このリポジトリの他の場所と同じく、境界を正直に書く:

- **0.7.5・Codespace 上で確認済み:** `setup.sh`（新規・再実行）、Stop フックの出力
  （セッションが残っている場合・残っていない場合・Colab CLI を入れていない場合）、`--serve` のページ。
- **0.7.5・Codespace 上で通しで実行済み（2026-11-07、CPU ランタイム）:**
  - **認証。** `auth.sh --url-only` → ブラウザ → `auth.sh --code` で完了した。
    `colab whoami` は `Auth provider: oauth2` と表示し、`colaboratory` スコープも付いている。
  - **`smoke_test.sh`。** 通った。VM は Python 3.13.18、GPU なし。
  - **ノートブック連鎖。** `colab_secrets.py` で Codespaces Secret の `GEMINI_API_KEY` を渡し →
    generator → MuJoCo アダプタを 1 セッションで流した。入力はサンプル動画。
    - generator は約 2 分。キャプションと Gemini による再分類も動き、
      `cbd_dataset.zip`（2.6 MB、122 ファイル）を出力した。
    - MuJoCo アダプタは約 1 分。CPU の `osmesa` でレンダリングし、受け入れ基準をすべて満たして
      `/content/human_behavior_demo_2_0/mujoco_adapter_output.zip`（0.3 MB、9 ファイル）を出力した。
    - どちらのログにも Traceback はない。データセットの欠け方はコミット済みのサンプルと完全に同じ
      （cup が写るのは 1 フレームだけ、interaction イベントは 0 件、face coverage は 0）。
  - **実行後。** `colab stop` → `colab sessions` で残りがないことを確かめた。キーの値は
    `ws/` にも `~/.config/colab-cli/`（CLI の履歴を含む）にも残っていなかった。
- **0.7.5 ではまだ確かめていない:**
  - セルが失敗したときの挙動。上の実行では失敗したセルがなかったため、「それでも終了コードは 0」は
    0.6.0 で確かめた内容のまま。
  - `input()` / `files.upload()` / `drive.mount()` の対処手順。
  - GPU ランタイム。
  - mediapipe_overlay と unity_vrm のアダプタ。

  運用ガイドのその他の挙動メモは **0.6.0** での実測。0.7.5 のソースで変化が分かった箇所
  （認証フロー、`jupyter-kernel-client` の固定、keep-alive デーモン）には印を付けてある。
- **ローカルマシンではまだ動かしていない。** ローカルで違うのはブラウザの開き方
  （`webbrowser.open`）とキーの出どころだけ。
- **最初の CBD 試走（2026-11-04、テンプレート側から）は認証の手前で中断した。**
  0.7.5 の導入と認可リンクの配信までは進んだが、`GEMINI_API_KEY` が Codespaces Secret として
  定義済みなのに別リポジトリにしか共有されておらず Codespace に届かなかったため、そこで止まった。
  上で共有手順を明記しているのはそのため。ヘッドレス対応表はその試走でのノートブックの読みを、
  ここでソースと突き合わせ直したもの。

どれかが動かなかったら、それ自体が知見なので issue にしてほしい。

## 由来

同じ作者による単体の Colab CLI セットアップ用テンプレート（`google-colab-cli` 0.6.0 で
Codespace 上で実測）を取り込んだもの。取り込み時の変更: 1ディレクトリに集約してパスを修正。
認証を 0.7.x 自身のフローの上に作り直した（0.6.0 用の loopback 補助は廃止）。
`colab_secrets.py` にローカルの `.env` 対応を追加。Stop フックを Python で書き直し（`jq` 不要）、
リポジトリ全体に登録した。公式 skill は同梱せずセットアップ時に生成。テンプレートでの CBD 試走（2026-11-04）の知見は、
上のヘッドレス対応表と Secret 共有の注記に反映した。引き継ぎメモそのものは持ち込んでいない —
記録されているのは一個人のアカウントとマシンで、読み手に必要な情報ではないため。
