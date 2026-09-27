# Finger SDK Tool

[![CI](https://github.com/Yuzuki-Midoshima/Finger-SDK-Tool/actions/workflows/ci.yml/badge.svg)](https://github.com/Yuzuki-Midoshima/Finger-SDK-Tool/actions/workflows/ci.yml)
![Maya](https://img.shields.io/badge/Autodesk%20Maya-2026-0696D7)
![Python](https://img.shields.io/badge/Python-3.x-3776AB)

Autodesk Maya向けの、**指のSDK（Set Driven Key）を自動構築するリギングツール**です。

![Finger SDK Tool](docs/images/finger-sdk-ui.png)


指ごとに何度も繰り返すドリブンキーの設定を自動化し、**ポーズデータを選んで実行するだけで、指コントローラーとSDKをまとめて構築できます。**

ポーズの数値はJSONとしてツール本体から分離しているため、  
Pythonコードを変更せずにポーズの追加・調整・再構築を行えます。

---

## 主な機能

- **指SDKの自動構築**  
  選択したポーズデータからDriver AttributeとDriven Keyをまとめて作成します。

- **複数ポーズをまとめて構築**  
  Fist / Relax / Spread / Flex Curlなど、必要なポーズを一度にビルドできます。

- **左右共通のポーズデータを使用**  
  `L_` / `R_` をツール側で判別するため、左右で同じデータを二重に管理する必要がありません。

- **ポーズ調整後の再構築**  
  既存SDKを整理してから再構築するため、調整 → 確認 → 修正を繰り返せます。

- **構築前のチェック**  
  必要なジョイントやポーズデータを確認し、不足がある場合は処理前に知らせます。

---

## 動作イメージ

![Finger SDK Pose](docs/gifs/finger_sdk_tool.gif)

多数の指Jointへ個別にDriven Keyを設定する代わりに、  
ツールから使用したいポーズを選択してSDKをまとめて構築します。

```text
ポーズを選択
    ↓
内容を確認
    ↓
SDKを構築
    ↓
Maya上で動作確認
    ↓
必要に応じてポーズを調整
    ↓
再構築
```

一度作って終わりではなく、  
**実際に指を動かして確認しながら何度でも調整できること**を重視しています。

---

# 機能説明

## ポーズライブラリ

![Pose Library](docs/images/finger-sdk-pose-library.png)

指のポーズをPythonコードへ直接書き込まず、  
**JSONファイルとして管理**します。

例えばFistやRelaxなど、それぞれのポーズに対して

- 使用するDriver Attribute
- Driverの値
- 各Jointの回転値

を保存します。

```json
{
  "pose_name": "fist",
  "driver_attr": "fist",
  "driver_value": 10,
  "joints": {
    "index1_jnt": {
      "rotateX": 0,
      "rotateY": 0,
      "rotateZ": -75
    }
  }
}
```

ポーズを変更するときはJSON側を編集するため、  
**SDKを構築するPython処理そのものを変更する必要がありません。**

---

## SDKの自動構築

![SDK Build Ready](docs/images/finger-sdk-build-ready.png)

使用したいポーズを選択し、`BUILD SDK`を実行します。

![SDK Build Confirmation](docs/images/finger-sdk-build-confirmation.png)

実行前に、

- Driver Attribute
- Driver Value
- 対象Joint数

などを確認できます。

![SDK Build Complete](docs/images/finger-sdk-build-complete.png)

Buildを実行すると、

```text
指コントローラー
      ↓
Driver Attribute
      ↓
SDK Curve
      ↓
指Joint
```

という接続を自動で構築します。

大量のDriven KeyをJointごとに手作業で設定する必要がなく、  
**同じルールで一貫した指SDKを作成できます。**

---

## 複数ポーズの一括構築

Ctrl / Shift / ドラッグによる複数選択に対応しています。

例えば、

```text
Fist
Relax
Finger Spread
Flex Curl
```

などのポーズをまとめて選択し一括でビルドできます。

ポーズごとに何度も同じ操作を繰り返す必要がないため、キャラクターセットアップ時の反復作業を減らせます。

---

## 左右の自動判別

ポーズデータでは、Joint名を

```text
index1_jnt
```

のように左右のPrefixを付けずに記述できます。

生成時にツール側で、

```text
L_index1_jnt
R_index1_jnt
```

として解決します。

これにより左右でほぼ同じポーズデータを二重に用意する必要がなく、  
**片側だけ修正されて左右差が生まれることも防ぎやすくなります。**

---

## 異なるJoint構成への対応

![Finger Joint Mapping](docs/gifs/finger-joint-mapping.gif)

RigごとにJointの命名規則や階層構造が異なる場合でも、
対象Jointを手動で指定できます。

通常は名前から対象Jointを自動判定しますが、
自動判定できない場合はUI上から各指のJointを指定できます。

また、1つ目のJointを指定すると、
その下の階層から子Jointを自動取得します。

親指についてはRig構成に合わせて、

```text
自動判定
第1節から（4段）
第1関節から（3段）
```

## ポーズ調整と再構築

![SDK Rebuild](docs/images/finger-sdk-rebuild-confirmation.png)

ポーズデータを修正したあとも、同じ操作でSDKを更新できます。

```text
既存SDK
   ↓
対象SDKを整理
   ↓
再構築
   ↓
更新されたSDK
```

Build対象に関連する既存SDKを整理してから再構築するため、  
同じポーズを繰り返しBuildしてもSDK Curveが重複しないようにしています。

このツールでは、

**作成 → 動作確認 → ポーズ修正 → 再構築**

という制作中の試行錯誤を前提にしています。


## コントローラー

左右のコントローラーの命名も任意で変更できます。

![NAME](docs/images/name.png)

コントローラーは


---

# 制作背景

Finger SDKを手作業で設定する場合、  
複数の指ジョイントに対して多くのドリブンキーを設定する必要があります。

キャラクターやポーズが増えると、

- 同じ設定作業を何度も繰り返す
- 左右で設定差が発生する
- JointやChannelの指定を間違える
- ポーズ修正のたびにSDK Curveを編集する
- キャラクター固有の数値がPythonコードへ増えていく

といった問題が起こりやすくなります。

そこで、  
**「SDKを作る処理」と「キャラクターごとのポーズ値」を分ける構成**にしました。

```text
ポーズデータ
   JSON
    ↓
データ確認
    ↓
左右・Joint名を解決
    ↓
共通の構築処理
    ↓
MayaのSDK
```

ポーズが変わっても構築処理は共通のまま使用できるため、  
キャラクターやポーズの追加に対応しやすくしています。

---

# 制作フロー

1. 対象のCharacter RigをMayaで開く
2. Finger SDK Toolを起動
3. 使用したいポーズを選択
4. Driver Attribute / Value / Joint数を確認
5. `BUILD SDK`を実行
6. 指コントローラーとSDKを自動構築
7. Maya上で指の動きを確認
8. 必要に応じてJSONのポーズ値を修正
9. 再度Buildして更新

```text
ポーズ選択
   ↓
確認
   ↓
構築
   ↓
動作確認
   ↓
ポーズ調整
   ↓
再構築
```

---

# データと処理の分離

このツールでは、  
**キャラクター固有のポーズ値とSDK構築処理を分けています。**

```text
ポーズデータ      → JSON
データ確認        → core.py
Maya上の構築      → builder.py
UI                → main.py
```

例えば新しいポーズを追加する場合、

```text
新しいポーズ
    ↓
JSONを追加
    ↓
データ確認
    ↓
既存の構築処理
    ↓
SDK完成
```

という流れになるため、  
ポーズごとに新しいPython処理を書く必要がありません。

---

# チーム制作を想定した構成

```text
TA / Programmer
      ↓
SDK構築処理

Rigger / Artist
      ↓
ポーズデータ
```

ポーズを調整するためにBuilder本体を直接編集する必要がないため、  
**処理ロジックとポーズ調整を分けて扱えます。**

JSONはテキスト形式なのでGit上で変更差分も確認しやすく、  
ポーズデータを共有・管理できます。

---

# 安全性

Build開始前に、

- ポーズデータ
- Controller
- Driver Attribute
- 使用するFinger Joint

などを確認します。

一部のJointが見つからない場合は不足しているJointを表示し、  
存在するJointだけで続行するか、処理を中止するか選択できます。

対象となるJointが1つも存在しない場合はBuildを開始しません。

また、Build処理は1つのUndo Chunkとしてまとめています。

処理中にエラーが発生した場合は、MayaのUndoを利用して  
可能な範囲で処理前の状態へ戻します。

---

# 内部構成

```text
                 Finger SDK Tool
                        │
          ┌─────────────┴─────────────┐
          │                           │
      ポーズデータ                    UI
         JSON                      main.py
          │                           │
          └─────────────┬─────────────┘
                        ↓
                     core.py
               データ確認 / 名前解決
                        ↓
                    builder.py
                  Maya Scene操作
                    SDK構築
                        ↓
                     Maya Rig
```

### `main.py`

- PySide UI
- ポーズ選択
- Build確認
- Progress表示
- Build Workflow管理

### `core.py`

- JSON読み込み
- ポーズデータ検証
- Joint名解決
- Mayaに依存しないデータ処理

### `builder.py`

- Controller生成
- Driver Attribute生成
- SDK Curve構築
- 既存SDKの整理
- Maya Scene操作

### `templates/`

- ポーズデータ
- キャラクター / ポーズ固有の設定値

---

# テスト

Mayaに依存しない処理を分離し、  
Pure PythonのUnit Testを実装しています。

```bash
python -m unittest discover -s tests -v
```

主に、

- JSON読み込み
- ポーズデータ検証
- Joint名解決
- 左右判定
- Missing Joint検出
- Rebuild時のCleanup

などを確認しています。

Mayaとの統合部分については、

- Controller生成
- 左右Build
- 複数ポーズBuild
- SDK再構築
- Curve重複防止
- Rollback
- Single Undo

を実際のScene上で確認しています。

### GitHub Actions

```text
Push / Pull Request
        ↓
Python構文チェック
        ↓
Unit Test
        ↓
結果
```

Python 3.9 / 3.11 / 3.13で、Mayaに依存しない処理のRegressionを確認しています。

---

# 技術情報

- Autodesk Maya 2022–2026
- Python 3
- maya.cmds
- PySide2 / PySide6
- JSON
- unittest
- GitHub Actions

### 主な技術要素

- JSONによるポーズデータと処理の分離
- JSON Pose Validation
- 左右Joint名の自動解決
- Set Driven Key Network構築
- 既存SDKの整理 / 再構築
- 重複しないRebuild
- Single Undo / Rollback
- Maya非依存処理のUnit Test

---

# 動作条件

- Autodesk Maya 2022–2026
- Python 3
- 対応するFinger Joint構造
- `L_` / `R_` Prefixを使用するRig

外部Python Packageは必要ありません。

付属のポーズデータはDiana RigのJoint Namingを基準にしています。

```text
L_index1_jnt
R_pinky3_jnt
L_thumb_palm_jnt
```

使用するRigのJoint名は、`templates/*.json`の定義と対応している必要があります。

---

# インストール

リポジトリをMayaのUser Scripts Directoryへ配置します。

```text
Documents/
└─ maya/
   └─ scripts/
      └─ Finger-SDK-Tool/
```

MayaでShelf Buttonを作成し、CommandのLanguageを **Python** に設定して、以下のコードを貼り付けます。

```python
from pathlib import Path
import importlib.util
import sys

import maya.cmds as cmds


tool_root = Path(cmds.internalVar(userAppDir=True)) / "scripts" / "Finger-SDK-Tool"
main_file = tool_root / "main.py"

if not main_file.is_file():
    cmds.error("Finger SDK Tool was not found: {}".format(main_file))

module_name = "_finger_sdk_tool_main"
sys.modules.pop(module_name, None)
spec = importlib.util.spec_from_file_location(module_name, str(main_file))
if spec is None or spec.loader is None:
    cmds.error("Could not load: {}".format(main_file))

module = importlib.util.module_from_spec(spec)
sys.modules[module_name] = module
spec.loader.exec_module(module)
module.show()
```


---

# 開発環境

- Autodesk Maya 2026
- Python 3.11
- Maya Python API
- PySide6
- shiboken6
- pytest

---

# License

MIT License

© 2026 Yuzuki Midoshima
