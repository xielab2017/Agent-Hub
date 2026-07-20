# EMP API Design

- 新建 `webapp/backend/helpers/agent_api.R`，集中实现环境目录、capabilities、allowed roots、路径解析和 preview。
- `plumber.R` 只 source helper 并增加三个 endpoint。
- session/job helper 的根目录初始化改为函数或环境解析结果；文件布局与序列化格式不变。
- allowed roots 使用平台路径分隔符解析；比较 normalized root 与 normalized candidate 的路径组件，不使用字符串前缀判断。
- preview 使用现有 `read_table_auto`、metadata/orientation helper，读取前先检查文件大小上限；响应不创建 session。
- import endpoint 调用共享的路径校验后，走与 multipart endpoint 相同的内部 import helper。若现有 endpoint 逻辑无法直接复用，先提取不改变行为的内部函数，再由两条路由调用。
