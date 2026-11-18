# 海洋数据挖掘

这个文件夹是独立的项目目录。当前已完成 100 万行的两次预试验及一次正式累计回本实验。尚未撰写报告。

## 文件放在哪里

```text
海洋数据挖掘/
├── pilot_parquet.py          预试验主程序
├── requirements.txt         Python 依赖及版本
├── README.md                本说明
├── docs/
│   └── 最小实验方案.md
├── data/pilot/1000000/
│   ├── random.parquet       模拟乱序数据
│   └── time_sorted.parquet  同一批数据的时间排序版
├── results/pilot/
│   ├── pilot_1m_run1.json    第一轮原始记录与汇总
│   └── pilot_1m_run2.json    第二轮原始记录与汇总
└── archive/
    ├── pilot_parquet_original.py   产生历史结果的原脚本，仅作存档
    └── organization_manifest.json  整理记录与文件校验值
```

主程序根据自身位置寻找项目目录，因此可以整体复制或移动本文件夹，不需要修改数据路径。Python 运行环境需要在目标电脑另行准备。不要只移动主程序。

## 首次准备运行环境

先安装可用的 Python 3.12 或更新版本。在此文件夹打开 PowerShell，依次运行：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

依赖安装需要联网。无需激活虚拟环境，直接使用上面的 Python 路径即可。当前整理操作未创建虚拟环境，也未重新运行性能实验。

## 手动重跑预试验

```powershell
.\.venv\Scripts\python.exe .\pilot_parquet.py --rows 1000000 --label pilot_1m_run3
```

请使用新 label 保留已有结果。同名 label 会覆盖对应 JSON。程序会重新生成同规模的数据文件，并重复排序和计时，结束后将记录保存到 results/pilot/。现有 data 文件是最近一次预试验留下的数据。

主程序暂时只实现预试验，不能把其输出中的估算回本次数当成正式累计查询验证结果。查看方案中的正式实验安排后再实施下一阶段。

## 历史记录说明

现有两份 JSON 保持原样，其 script_sha256 对应 archive/pilot_parquet_original.py。当前主程序只调整了项目路径和结果目录创建逻辑，未改变数据生成及实验方法。整理清单记录了新旧脚本校验值和复制文件的完整性核对结果。

未来可以在 docs/ 下保存研究笔记，在 conversations/ 下保存完整 AI 聊天记录，在 report/ 下保存最终报告。现在尚未生成聊天导出或报告。

## GitHub

.gitignore 默认忽略可再生成的数据、虚拟环境及 Python 缓存。代码、实验方案、JSON 原始结果和完整聊天 Markdown 可以纳入版本管理。当前尚未创建或上传 GitHub 仓库。


## 正式实验文件（2026-11-17）

- `formal_experiment.py`：冻结参数后执行真实整批查询计时；已有 run-id 目录会拒绝覆盖。
- `plot_formal.py`：只读取正式结果，生成图表与机器可读汇总，不重跑实验。
- `docs/正式实验执行清单.md`：执行前确定的条件、回本定义和数据保护规则。
- `results/formal/formal_20261117_01/`：本次正式实验全部记录。
  - `config_frozen.json`：计时前冻结的计划、查询序列及原始预估。
  - `events.jsonl`、`measurements.json`：逐组原始计时。
  - `preparation.json`：三次重排成本、正确性与行组检查。
  - `summary.json`：回本区间和重排成本敏感性。
  - `diagnostics.json`：基于已有数据的补充检查，明确与预先计划区分。
  - `cumulative_time.png` / `.svg`：累计耗时图。
  - `net_saving_zoom.png`：交点附近配对净节省图。
- `data/formal/formal_20261117_01/`：正式实验重排文件，原始文件仍使用现有预试验数据。

在准备好依赖的环境中重新运行时，请用新的 run-id。单独重绘本次图表可运行：

```powershell
python .\plot_formal.py --run-id formal_20261117_01
```

本机另在 `.deps/` 安装了依赖，正式实验与绘图脚本会优先读取该目录；迁移到其他电脑时建议按 requirements.txt 重新安装。完整 AI 对话尚未导出，GitHub 尚未上传。
