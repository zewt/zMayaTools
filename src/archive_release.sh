#!/usr/bin/bash
VERSION=`git describe --tags --dirty`
OUTPUT=$VERSION.zip
git archive HEAD -o $OUTPUT
zip -r $OUTPUT plug-ins/bin
echo Wrote: $OUTPUT

