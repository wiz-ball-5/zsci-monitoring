# ZSCI Monitoring — Step 4

目标：在你自己的浏览器第一次打开真正可交互的 ZSCI Monitoring Dashboard。

## 1. 解压并进入目录

```bash
cd /mnt/d/zsci-monitoring-step4
```

## 2. 安装网站依赖

继续使用 Step 3 成功的 Python 环境：

```bash
python -m pip install -r requirements.txt
```

## 3. 导入 Step 3 已生成的数据

如果你的成功项目目录是 `/mnt/d/zsci-monitoring-step3`：

```bash
python import_step3_outputs.py ../zsci-monitoring-step3
```

如果实际目录是 `zsci-monitoring-step3.1`，把上面的目录名换成它。

## 4. 检查数据

```bash
python check_dashboard_data.py
```

最后必须看到：

```text
RESULT: PASS
```

## 5. 可选：测试网站绘图代码

```bash
python -m pytest -q test_dashboard.py
```

## 6. 启动网站

```bash
python app.py
```

终端会显示本地地址。不要关闭这个终端。

## 7. 用 Windows Chrome / Edge 打开

地址栏输入：

```text
http://127.0.0.1:8050
```

或者：

```text
http://localhost:8050
```

如果 Python 在 WSL 里运行，现代 WSL 一般可以直接从 Windows 浏览器访问 localhost。

## 8. 停止网站

在运行 `python app.py` 的终端按：

```text
Ctrl + C
```

## 页面现在包含

- Current MTD ZSCI
- Latest daily OISST ZSCI
- Latest finalized 5-month HadISST ZSCI
- OISST MTD coverage
- 120-day OISST interactive chart
- Historical HadISST interactive chart
- ZSCI v1.0 definition/method说明

Step 4 故意不让网页自己下载 NOAA 数据。网页只读取 Step 3 生成的小 CSV/JSON。
Step 5 才会把“更新数据 → 网站发布”自动化。
