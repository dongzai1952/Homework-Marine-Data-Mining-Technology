# 海洋数据挖掘：Parquet 排序收益边界

> **AI 协作聊天记录：[点击查看 AI聊天记录.md](./AI聊天记录.md)**
>
> **文件名：`AI聊天记录.md`｜位置：仓库根目录（`/AI聊天记录.md`），与本 README 同级。**
> 保留指定聊天的用户消息、AI 回复和原始顺序；记录截止位置及范围见文件首部。

研究范围：同一份模拟观测表中，一天／七天时间查询的累计成本，以及固定一天时窗口跨行组的影响。已有实验均在预热条件下完成；报告不提供通用的“超过多少次就应排序”建议。

**当前正式论文：[PDF（15 页，根目录提交副本）](模拟海洋观测表的Parquet排序收益边界_正式版.pdf) · [paper 内同版本 PDF](paper/main.pdf) · [LaTeX 主文件](paper/main.tex) · [原创探索专章](paper/innovation.tex) · [完整编译与材料生成说明](paper/README.md)。**

作者：陈立冬，学号：22634016，授课教师：张帆。
GitHub 地址：[Homework-Marine-Data-Mining-Technology](https://github.com/dongzai1952/Homework-Marine-Data-Mining-Technology)。已通过不带认证的 GitHub API 确认仓库为 Public，当前远程为空；本地材料已整理，上传及文件匿名访问验证尚未完成。最新状态以 [提交状态](提交状态.md) 为准。

当前论文由 14 页“原创探索详解版”完整材料包同步，保留第 5 节并补齐六对配对表和运行目录差异，现为 15 页。替换前的论文与项目 README 独立保存在 `archive/paper_history/`；导入来源与哈希见 [同步记录](paper/audit/import_sync.json)。

- 论文材料只读核查：`python paper/tools/build_materials.py verify`；重建数值宏、配对表和矢量图见 [paper/README.md](paper/README.md)，不重新计时。
- [Markdown 报告 v2](report/完整报告_v2.md)、[v1](report/完整报告_v1.md) 为历史版本，保留原文，不作为当前正式论文入口。
- [v2 复现验证记录](docs/复现验证记录_v2.md)、[修改清单](docs/修改清单_v2.md) 记录当时已做和未做的验证；其中“尚无仓库”等状态是历史描述。

下文为既有实验复现说明；本次论文同步未重新执行其中的性能实验。


## 正式提交入口

- [指定聊天原始文本 Markdown](AI聊天记录.md)：24 条用户消息、86 条 AI 回复，按原顺序保留，覆盖从选题开始至文件首部注明的本次提交快照边界；不是协作摘要。
- [聊天导出核查](docs/submission/chat_export_audit.json)：分页终止、消息 ID、顺序和逐条文本哈希。
- [正式版本冻结清单](docs/submission/frozen_paper_manifest.json)、[提交状态与待办](提交状态.md)、[继续上传与匿名核查](docs/submission/上传与核查说明.md)。根目录正式 PDF 与 `paper/main.pdf` 字节相同。
- 完整实验记录见 `results/`；只读核查与重跑说明在下文，论文编译说明见 `paper/README.md`。

论文正文、源码、图表和历史实验记录在本次收尾中不再修改。论文及旧核查文件内“本次未上传”“尚未核查”等语句反映其形成时状态，当前提交状态单独更新，不倒改历史记录。

另一聊天“查找海洋数据挖掘对话”不在本次指定聊天的导出范围；原创新章节的材料已同步，但其单独完整对话尚未纳入提交。指定聊天导出之后产生的本轮操作消息也不在该固定快照中，后续需要时应另行追加真实记录。

`.gitattributes` 禁用自动换行转换，以保留历史文件的 SHA-256；不要批量改写历史脚本或结果的换行格式。

本地历史论文备份 `archive/paper_history/` 不上传；原始实验脚本、结果、冻结规则和旧报告仍保留并提交。数据、依赖、缓存及复现输出按 `.gitignore` 排除；需要时按复现说明生成。

## 先选操作目的

| 目的／命令 | 需要原始数据吗 | 会重新性能计时吗 | 会写什么 |
|---|---|---|---|
| 阅读报告、原图、JSON | 否 | 否 | 不写文件 |
| `verify-history` | 否；存在时额外检查哈希 | 否，也不连接 DuckDB | 默认只打印；`--out` 可另存核查记录 |
| `analyze-errors` | 否 | 否 | 新目录中的事后误差 JSON／Markdown |
| `render-history` | 否 | 否 | 新副本中的派生图表／汇总；不改原仓库 |
| `create-workspace` | 否 | 否 | 独立副本及来源哈希清单 |
| `generate-data` | 从代码生成 | **不采集性能计时**；会实际生成、排序并写出文件 | 副本中的两份 Parquet、生成与哈希记录 |
| `prepare-supplement` | 是 | 否；会执行不计时的正确性查询 | 新窗口清单、配置、冻结规则及接口哈希 |
| `run-main`／`run-pilot`／`run-supplement` | 主实验／补充需数据；预实验自行生成 | **是** | 新 ID 的计时结果；预实验会重写副本中的 pilot 数据 |
| `analyze-main`／`analyze-supplement` | 只需对应新运行结果 | 否 | 新运行 ID 下的汇总与图表 |

新入口是 [tools/reproduce_v2.py](tools/reproduce_v2.py)。历史 `*.py` 文件不改字节；新入口增加独立副本、数据生成、路径映射和防覆盖检查。历史脚本内部仍可能有旧路径，**不要直接执行 `archive/pilot_parquet_original.py`，也不要在历史仓库根目录直接运行有写入行为的旧脚本**。

## A. 新下载后，只核查历史结果（推荐先做）

取得完整项目 ZIP 后解压，或在确认仓库可访问后 clone。下列 PowerShell 命令从**实际下载的项目根目录**执行，不要求 E 盘或原作者用户名。先安装／选择 Python 3.12；`python --version` 应显示 3.12.x，本轮验证实际使用 3.12.14。若 `python` 未加入 PATH，用已安装 Python 的绝对路径替代命令中的 `python`。不需要 Codex 专用解释器。

```powershell
Set-Location -LiteralPath '你实际解压的项目目录'
python --version
python .\tools\reproduce_v2.py verify-history
```

此命令只使用标准库；无需 pip、`.deps`、网络、Parquet 文件或原 E 盘目录。检查主实验与补充实验产物清单、冻结清单、脚本／预实验参数哈希，以及主实验 190 个成对记录的序列和 38 个条件点的百分比计算。无数据时明确报告 `absent`，不会访问冻结记录里的旧绝对路径。它**不能重新证明查询返回值正确、磁盘 I/O 或历史计时环境**；这里只核查留存证据及其内部一致性。哈希基准本身不是第三方签名。

读取现成误差对照：[完整 76 点表](results/posthoc/error_metrics_v2/error_comparison.md)、[机器可读结果](results/posthoc/error_metrics_v2/error_comparison.json)。如果希望自己重新计算：

```powershell
python .\tools\reproduce_v2.py analyze-errors --out .\review_output\errors_local_01
```

输出目录必须不存在。计算使用原两轮预实验参数，分别对主实验全部 19 个次数、两种窗口长度计算误差；不修改旧 `criteria_audit.json`，也不重新计时。

## B. 安装环境（仅生成数据、重绘或重跑时需要）

支持说明以本次实际验证的 **Windows x64、Python 3.12.14** 为准；其他平台／Python 版本尚未验证。生成与性能实验需要 DuckDB；旧绘图脚本还需要 matplotlib、NumPy 和 `C:\Windows\Fonts\msyh.ttc`（微软雅黑）。`render-history` 在缺字库时会提前报错；无需重绘也能阅读仓库内已有 PNG。

```powershell
python -m venv .venv
$experimentPython = (Resolve-Path .\.venv\Scripts\python.exe).Path
& $experimentPython -m pip install -r .\requirements-repro-v2.txt
& $experimentPython -m pip check
```

无需激活虚拟环境，不涉及 PowerShell 的脚本执行策略。不要设置旧 `PYTHONPATH` 或把本机 `.deps` 复制进新仓库。若当前终端原先设置过 `PYTHONPATH`，为避免混入旧依赖，可先 `Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue`。

原 [requirements.txt](requirements.txt) 的三项主依赖不变：DuckDB 2.0.0、matplotlib 3.11.2、NumPy 2.5.5。新增 [requirements-repro-v2.txt](requirements-repro-v2.txt) 锁定本轮新虚拟环境安装到的完整依赖版本；它是**复现环境记录，不是事后补造的历史环境锁文件**。本轮干净虚拟环境安装成功，pip 使用了本机缓存；未证明完全无缓存下载或其他机器安装一定成功。网络不可用时，A 流程仍可执行。不要通过升级 DuckDB 来绕过生成数据的哈希不一致。

### 仅从历史结果重绘（不计时）

```powershell
& $experimentPython .\tools\reproduce_v2.py render-history --out .\review_output\figures_local_01
```

该目录必须不存在。此操作复制历史结果后，依次执行旧标准复核、主实验出图和补充实验出图；既不生成数据，也不执行性能查询。新图在副本的 `results/formal/formal_20261117_01/`、`results/supplement/boundary_20261118_01/` 下。图表元数据、SVG 标识或渲染环境可能改变文件哈希；副本中的旧图表清单不再代表新图，不应再将这个副本当作未修改的历史仓库核查。原仓库及报告引用的原图不变。

## C. 准备数据与独立实验副本

数据是模拟数据，不需要申请海洋数据下载权限。`data/` 默认不提交 GitHub；依赖包、虚拟环境也不提交。生成 SQL 直接从保留的 `pilot_parquet.py` 提取：100 万行、hash 输入常量 1729、30 天时间、六字段；按相同 DuckDB 版本、ZSTD level 3、65536 目标行组大小生成。

```powershell
# 仍在下载的项目根目录。保留上面的 $experimentPython。
$sourceProject = (Get-Location).Path
$replayProject = Join-Path $sourceProject 'reproductions\replay_local_01'
& $experimentPython .\tools\reproduce_v2.py create-workspace --workspace $replayProject
Set-Location -LiteralPath $replayProject
& $experimentPython .\tools\reproduce_v2.py generate-data
& $experimentPython .\tools\reproduce_v2.py verify-history
```

`create-workspace` 只接受新目录，复制脚本、历史记录、版本化入口及依赖文件，不复制原始数据或 `.deps`。`replay_v2.json` 保存复制来源及文件哈希。`generate-data` 只允许在该副本中执行；如果已有 `data/` 会拒绝覆盖。它生成：

| 文件（副本内相对路径） | 历史 SHA-256 |
|---|---|
| `data/pilot/1000000/random.parquet` | `1decfa8a5bf59125650d45b12d1b7ab2d94e3cda437ef40ed1e95954e342b46b` |
| `data/formal/formal_20261117_01/time_sorted.parquet` | `5ee088818b95ce2c6517d4f95ec0a36b718265863278d18e3ec21293f814ea09` |

该生成步骤确实执行了一次排序，但**不采集耗时，也不会将生成过程的耗时作为历史 R 或新实验 R**。两份文件均与历史哈希对比，记录在 `data_generation_v2.json`；不一致就报错停止，不能用不一致数据覆盖历史证据。它复现的是历史输入文件；补充实验继续沿用历史 R，而新主实验会独立测量自己的 R。

## D. 重新运行性能实验（以下命令本轮未执行）

先完成 C，当前目录是新副本。运行 ID 只用英文字母、数字、下划线或连字符，且必须为新 ID。旧结果不覆盖，运行失败留下的部分记录也不删除；另建副本或使用新 ID 诊断。不要加 `python -O`，旧脚本中的断言参与正确性检查。

### 主实验：实际重新排序、预热和整批计时

```powershell
& $experimentPython .\tools\reproduce_v2.py run-main --run-id formal_local_01
& $experimentPython .\tools\reproduce_v2.py analyze-main --run-id formal_local_01
```

前一条会重新测三次读／排／写成本及所有历史设计的查询批次；后一条只分析这次新保存的结果，生成累计图、10% 分类和总耗时误差复核。结果位于 `results/formal/formal_local_01/`；数据位于 `data/formal/formal_local_01/`。主实验依旧读取保存的两个历史 pilot 参数，不能把它说成在本次新机器上又重新训练／估计了预测参数。

### 补充实验：先准备与冻结，后实际计时

```powershell
& $experimentPython .\tools\reproduce_v2.py prepare-supplement --run-id boundary_local_01
# 在继续前阅读新目录中的 protocol_frozen.md 和 windows_frozen.json。
& $experimentPython .\tools\reproduce_v2.py run-supplement --run-id boundary_local_01
& $experimentPython .\tools\reproduce_v2.py analyze-supplement --run-id boundary_local_01
```

新接口调用未修改的历史函数，只重定向 RUN／OUT；选择规则、次数、种子与计时逻辑不变。新准备的配置引用副本内的文件，因此无需旧 E 盘路径；运行前同时检查历史脚本哈希与新接口哈希。**保持原补充设计：使用历史主实验输入及 R=0.5079524 秒，不自动改用 `formal_local_01` 的 R**，不能把输出说成与新主实验同批的比较。准备和运行之间不要搬动副本；新配置仍保存当前副本绝对路径，搬动后应在新位置重新 prepare 新 ID，不能手改已冻结配置。

### 可选：重新运行原预实验

```powershell
& $experimentPython .\tools\reproduce_v2.py run-pilot --label pilot_local_01
```

该命令会重新生成副本内 `data/pilot/1000000/` 数据并执行旧预实验全部计时；新标签只保护结果 JSON，**不表示数据文件不重写**。因此需要时单独新建一个副本操作。新 pilot 结果不会自动替换历史两个 pilot，也不会自动被 `run-main` 当作预测输入。本报告没有增加这种新参数来源实验。

## E. 哪些验证已做、哪些未做

本轮在新建虚拟环境及一个不含数据／`.deps`、路径含中文和空格的副本中完成：依赖安装与 `pip check`、无数据历史核查、76 点误差重算、两份数据生成并匹配历史哈希、补充 prepare 的 12 个窗口／24 次布局查询与原清单一致、无计时的历史图表重绘。新的分析入口还用**复制并明确标注的旧测量记录**做了接口验证，没有伪装成新测量。

本轮**没有执行**新入口的 `run-main`、`run-pilot`、`run-supplement` 成功计时路径，因用户要求不重跑；仅检查其接口、导入与防覆盖失败路径。没有在真正新电脑、Linux/macOS、不同 Python 版本验证，也没有实际 Git clone（尚无仓库）或无缓存安装验证。详细证据与限制见 [复现验证记录](docs/复现验证记录_v2.md)。

## 目录与提交边界

- `results/pilot/`、`results/formal/formal_20261117_01/`、`results/supplement/boundary_20261118_01/`：历史证据，保留字节。
- `results/posthoc/error_metrics_v2/`：本轮事后误差分析，独立于历史复核。
- `paper/`：当前正式论文、独立创新探索章节、源码、文献、图像、生成入口和核查记录。
- `report/`：历史 v1、v2、原图和引用核查；图片使用相对路径。
- `tools/reproduce_v2.py`：新增运行入口；原根目录脚本继续保留。
- `archive/README_before_v2.md`：修改前 README；`archive/pilot_parquet_original.py`：原预实验脚本。
- `docs/`：方法、历史章节、验证记录与本轮修改清单。
- `.gitignore` 排除 `data/`、`.venv/`、`.deps/`、`.cache/`、`reproductions/`、`review_output/`；不要把新测量或重绘图混入历史目录提交。

作者、学号、教师及仓库链接已在当前论文填写，未提供的其他身份信息不设待填项。提交前仍需导出、核对并提供两个聊天的完整 Markdown，确认仓库公开可访问；协作摘要不能替代完整记录。本次未上传 GitHub。
