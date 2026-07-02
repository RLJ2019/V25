# ChatGPT Validation – V25.1.2d

Validated locally:
- compileall: OK
- smoke_test: OK
- unittest discovery: OK

Purpose:
- prevent cached notification-state rows from causing false fail when `SHADOW_COMPARE_SINCE_UTC` points to a window with zero eligible pick rows.
