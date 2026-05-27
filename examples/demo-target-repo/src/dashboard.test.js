import assert from "node:assert/strict";
import test from "node:test";

import { addBugButtonLabel, emptyBugListMessage } from "./dashboard.js";

test("empty list uses bug-specific copy", () => {
  assert.equal(emptyBugListMessage([]), "暂无待处理 Bug");
});

test("add button describes the created item", () => {
  assert.equal(addBugButtonLabel(), "新增 Bug");
});
