#!/bin/bash

# We need to use Plesk's `filemng` command to lower privileges.
# We also need to pass request data via stdin, secure tmp file, or environment variables.
# `pm_ApiCli::callSbin` doesn't expose stdin and has a limit on env var length, so the only option left is
# to use a tmp file.
# However, since on the other side of `filemng` we have less privileges, it is not trivial.
# To resolve this we will simply read the file after `callSbin`, but before `filemng`.
# It's ugly, but it works.
cat "$I360_REQUEST" | plesk sbin filemng "$@"
exit_code=$?
rm -f "$I360_REQUEST"
exit $exit_code
