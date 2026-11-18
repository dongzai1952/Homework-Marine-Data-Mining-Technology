# 当前课程论文：原创探索详解与审查完善版

当前 `main.pdf` 共 **15 页**。导入材料包原版为 14 页，新增第 5 节“原创探索与创新点的具体拆解”；本轮保留该章，补充六对窗口配对结果表、C／E 盘运行目录差异与论文材料生成入口，因此页数增加。未新增实验或修改历史测量。

- `main.tex`：论文主文件；`innovation.tex`：第 5 节，保留两个 AI 对话的真实协作归属。
- `metadata.tex`：陈立冬、22634016、张帆和用户提供的 GitHub 链接。
- `data_macros.tex`：97 个历史数值宏；`generated/paired_savings.tex`：从原始单次记录计算的六对结果表。
- `references.bib`：文献；`figures/`：矢量面板与原 SVG。
- `tools/build_materials.py`：版本化论文材料生成与核查入口。
- `audit/`：当前检查、来源与生成记录；`audit/imported_revision/`：导入包的历史检查记录（14 页版本），不代表当前页数。

## 1. 只编译论文：不需要 Python、原始数据或实验结果

保持整个 `paper` 目录完整。在安装 TeX Live、XeLaTeX、Biber 的环境下，从 `paper` 目录运行：

```text
xelatex -interaction=nonstopmode -halt-on-error main.tex
biber main
xelatex -interaction=nonstopmode -halt-on-error main.tex
xelatex -interaction=nonstopmode -halt-on-error main.tex
```

Windows 可运行 `./compile.ps1`。本机已实际重新编译；全部资源使用相对路径。中文优先使用宋体、黑体、楷体等 Windows 字体，源码保留 Fandol 回退；其他系统最终字体映射与分页未验证。编译不执行实验。

## 2. 只核查论文材料：Python 标准库，无需 DuckDB

以下命令从**完整项目根目录**运行，需保留 `results/` 历史 JSON 与 SVG；独立论文材料包不含完整实验仓库。

```powershell
python .\paper\tools\build_materials.py verify
```

只读检查 97 个数值宏及来源清单、六对配对表、76 个误差点、源文件与图像哈希。没有 SQL 查询、数据生成或性能计时。若把论文放在别处，可显式指定 `--project-root '实际项目目录'`；脚本没有写死本机 E 盘路径。

## 3. 从历史 JSON 与 SVG 重建论文材料：输出必须是新目录

```powershell
python -m venv .venv-paper
$paperPython = (Resolve-Path .\.venv-paper\Scripts\python.exe).Path
& $paperPython -m pip install -r .\paper\requirements-materials.txt
& $paperPython .\paper\tools\build_materials.py generate --out .\review_output\paper_materials_01
```

`generate` 从主／补实验 JSON 重算数值宏与配对表，复算 76 个误差点，再将历史原 SVG 转换成 PDF 并按记录坐标裁取面板。输出包含 `data_macros.tex`、`generated/`、`figures/` 和 `audit/`，不包含论文正文，不自动覆盖当前论文。坐标、数据点和原 SVG 不变。新结果应核对后再采用。

这是生成**排版材料**，不是重新生成实验数据，也不是重跑性能实验。输出已存在、落入历史 `results/` 或当前 `paper/` 内时会拒绝操作。生成记录保存输入哈希、脚本哈希、软件版本和裁剪坐标。PDF 元数据可能影响字节哈希；其他环境应核查渲染结果，不能只凭整图 PDF 哈希不同就判断实验数据改变。

已实际验证：在本机现有 svglib 2.4.0、ReportLab 5.1.0、pypdf 6.21.4 环境，两次生成至独立新目录；97 个宏不变，六对表与历史汇总一致，四个裁取面板与导入版哈希一致。随后对当前论文运行标准库 `verify`。本轮未新建上述虚拟环境或重新执行 pip 安装；其他机器安装与渲染尚未验证。

## 4. 历史、状态与检查

替换前的 11 页 `paper` 与根目录 README 已独立备份，位置见 `audit/import_sync.json`。原始实验记录、脚本和旧 Markdown 报告不变。导入的第 5 节已解决此前贡献拆解不足，本轮只补结果交叉引用，并将“返回记录规模”改为更准确的“命中记录规模”（查询返回聚合结果）。

当前核查见 `audit/final_verification.json`、`audit/本轮完善说明.md`。公开仓库地址已填写，但公开可访问性与两个聊天的完整 Markdown 导出仍未核验；本轮没有上传 GitHub。后续编辑论文后需重新编译和检查。
