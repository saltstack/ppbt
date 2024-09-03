#!/bin/sh
#
# Build a ppt wheel in a docker container.
#
if [ -n "$UID" ]
then
  CHOWN=""
else
  CHOWN="chown -R $UID dist build src/ppbt/_toolchain"
fi

export CHOWN

CMD="
apt-get update;
apt-get install -y gcc python3 \
   python3-pip python3-venv flex make \
   texinfo unzip help2man gawk libtool-bin libncurses5-dev \
   bison wget rsync
cd /src
python3 -m venv venv
venv/bin/pip install build wheel setuptools
venv/bin/python3 -m build
$CHOWN
"

docker run --rm -v $(pwd):/src debian:11 /bin/sh -c "$CMD"
