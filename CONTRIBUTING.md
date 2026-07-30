# 参与贡献

感谢你对 Any Auto Register 的关注！欢迎提交 Issue 和 Pull Request。

## 开发环境

```bash
python3 -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## 运行测试

```bash
pytest
```

运行单个测试文件：

```bash
pytest tests/test_api_health.py -v
```

## 提交规范

使用 [Conventional Commits](https://www.conventionalcommits.org/)：

- `feat:` 新功能
- `fix:` 修复
- `docs:` 文档
- `refactor:` 重构
- `test:` 测试
- `chore:` 构建/工具

## 添加新平台

1. 在 `platforms/` 下新建目录
2. 实现 `plugin.py`（继承 `BasePlatform`，用 `@register` 装饰器注册）
3. 实现 `protocol_mailbox.py`（协议模式注册逻辑）
4. 可选：实现 `browser_register.py` 和 `browser_oauth.py`
5. 在插件类上声明平台能力（类属性）：`supported_executors`、`supported_identity_modes`、
   可选的 `supported_oauth_providers` 和 `capabilities`。首次启动会据此写入
   `platform_capability_overrides` 表；后续启动做增量合并。
   **不要**再写 `resources/platform_capabilities.json` —— 该文件已在 `da2bbb3` 删除。
   漏掉这一步，插件仍会注册并出现在界面上，但用户一启动任务就会失败。
6. 添加对应的测试

## 代码风格

- Python 代码遵循 PEP 8
- 类型注解尽量完整
- 新增的注释和文档字符串遵循"中文在前，英文在后"的双语格式（与 `catalog-conventions.md` 的双语约定一致）；新增的用户可见日志改用带 key 的路径（`i18n_key`/`i18n_params`，格式见 `catalog-conventions.md` 的 "Task log records" 一节），不再新增硬编码中文日志；仅供控制台/内部使用、不面向用户的日志（`print()`/`logging`）不受此项影响，继续使用中文；通过上游合并（upstream merge）引入的代码，在下次被修改前豁免以上要求；该豁免按"行"粒度生效——只有新增或修改的行才需要满足双语要求，未被触及的相邻行不受影响；修改函数体本身不要求随之修改其文档字符串，除非文档字符串本身也被修改。

  New comments and docstrings are Chinese first, then English (matching `catalog-conventions.md`'s bilingual format); new user-visible log lines use the keyed path (`i18n_key`/`i18n_params`, format specified in `catalog-conventions.md`'s "Task log records" section) instead of a new hardcoded Chinese string; console-only/internal logging (`print()`/`logging`, invisible to users) is unaffected and stays Chinese; code arriving via an upstream merge is exempt from this rule until it is next touched; this exemption applies at line granularity — only the lines added or changed need to satisfy the bilingual requirement, untouched neighbouring lines are unaffected; editing a function body does not itself require changing its docstring, unless the docstring itself is also changed.
