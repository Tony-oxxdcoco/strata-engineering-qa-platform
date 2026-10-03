# 受控 CSV 输入契约

这是 STRATA 合成演示格式，不是原生 ETABS／SAFE 导出。它向与 JSON 样例相同的 schema `1.0` 和确定性检查提供输入，不调用求解器、不推断缺失字段、不生成反力、不认证来源真实性。本文记录保留在 `dist/` 的解析模块。

## 界面调用接口

```js
import { parseControlledCsv, controlledCsvTemplate, ControlledCsvError } from './csv.js';

// The caller checks the selected File size before reading, then passes its text.
const input = parseControlledCsv(await file.text(), { filename: file.name });
// Pass input to the existing createRun(input) / runChecks(input).
const templateText = controlledCsvTemplate(); // UTF-8, CRLF, downloadable text/csv
```

`parseControlledCsv` 返回含 importMetadata 的已验证输入。失败抛出 ControlledCsvError，包含可读 message、从 1 开始的物理 row、CSV 字段 column、columnName 和 code。错误码：`CSV_INVALID`、`CSV_SYNTAX`、`CSV_HEADER`、`CSV_VALUE`、`CSV_LIMIT`、`CSV_DUPLICATE`、`CSV_MISSING_RECORD`。缺记录在文件结尾报告。错误和导入字段应显示为文本，不是 HTML。

模块不联网、不自行写存储、不依赖第三方包，只引用现有引擎校验器和样例生成器。调用者创建运行时，导入来源信息成为输入快照的一部分，也纳入运行哈希。

## 表头与记录

十一列名称必须各出现一次，可以调整顺序。名称和单位区分大小写；额外列以及不适用但非空的单元格报错。

```csv
record_type,id,floor_id,case_id,support_id,value,unit,evidence_ref,title,locator,content
```

| record_type | 必填单元格 | 含义 |
|---|---|---|
| metadata | id, value | 必须为 `schemaVersion,1.0` 和 `synthetic,true`，CSV 仅支持合成案例。 |
| project | id, value | name 必填；revision、description、software 可选，提供后保留。 |
| scope | id, value | 必需 ID：basis、selfWeight、reactionPositive，保留值供引擎判断。 |
| units | id, unit | 必需 ID：area、surfaceLoad、force，声明单位必须被支持。 |
| floor | id, value, unit, evidence_ref | value 是楼层面积，严格大于零。 |
| requirement | id, floor_id, case_id, value, unit, evidence_ref | value 是独立提供的所需面荷载 q。 |
| assignment | id, floor_id, case_id, value, unit, evidence_ref | value 是分配的楼层总力。 |
| support | id | 独立提供的支座 ID。 |
| reaction | id, support_id, case_id, value, unit, evidence_ref | value 是独立提供的竖向反力 fz。 |
| evidence | id, title | locator 和 content 是提供的来源信息；空正文保留，由引擎证据校验阻断。 |

每行都有 record_type，至少一个楼层。其他工程列表可空，由引擎报告覆盖不足。value 为有限、非负十进制数，允许科学计数；不允许千位分隔、十六进制、NaN、无穷或下溢转零。转换使用 JavaScript 有限精度数，ID 和必需文本最多 2,000 字符。

演示范围：`basis=unfactored-static-gravity`、`selfWeight=excluded`、`reactionPositive=upward`。其他明确范围值保留，并阻断相关数值验证。此导入不增加组合或任意工况支持。

## 单位与证据

| 量纲 | 支持的单位拼写 | 引擎单位／转换 |
|---|---|---|
| 面积 | `m2`、`m²` | m2，数值不变 |
| 力 | `kN`、`N` | kN；N 除以 1,000 |
| 面荷载 | `kN/m2`、`kN/m²`、`kPa`、`N/m2`、`N/m²` | kN/m2；N/m2 除以 1,000，其余不变 |

每个数值行都必须声明单位，即使与文件 units 记录相同。同量纲允许混用支持单位。units 记录只保存来源声明，不能补缺失行单位或覆盖明确的行单位。未知单位拒绝导入，输出 units 始终采用引擎单位。

现有引擎需要 evidence ID：`design-brief`、`model-export`、`reaction-export`、`support-schedule`、`review-note`。楼层和要求引用 design-brief，分配引用 model-export，反力引用 reaction-export。导入保留这些引用；缺证据行、空正文或无效引用不补齐，由引擎按需要返回 NOT VERIFIED。

重复 requirement／assignment／reaction 行保留，包括重复记录 ID 和工程键，供 QA-001 返回 FAIL。重复 floor／support／evidence ID 在输入结构中有歧义，因此报错并给出对应 CSV 行。没有静默去重。

## 来源追踪

```js
input.importMetadata = {
  format: 'strata-controlled-csv',
  version: '1.0',
  filename: 'example.csv',
  declaredUnits: { area: 'm2', surfaceLoad: 'kPa', force: 'N' },
  rows: [{
    row: 23, // starting physical line; quoted multiline text counts its lines
    recordType: 'assignment',
    recordId: 'A1',
    target: 'assignments[0]',
    field: 'force',
    originalValue: '3000000',
    originalUnit: 'N',
    normalizedValue: 3000,
    normalizedUnit: 'kN'
  }]
};
```

每条导入数据记录都有行／类型／ID／目标位置。数值记录还保留原始数字文本、原单位、转换后数字和单位。这是 CSV 转换轨迹，不是独立认证的工程依据。

## CSV 语法与限制

支持开头 UTF-8 BOM、CRLF／LF 换行、引号内逗号、双引号转义（`""`）及引号内换行，引号内文本保留。未加引号字段内出现引号、闭合引号后不是分隔符、引号未闭合或列数不符均拒绝。空行忽略，但计入物理行号。

编码文本最多 **1,048,576 UTF-8 字节**，最多 **5,000 条数据记录**，每个工程列表最多 **1,000 条**。汇总或计算值溢出也拒绝输入。`dist/examples/controlled-template.csv` 由 controlledCsvTemplate() 生成，回读后保留正确样例的工程值和证据。
