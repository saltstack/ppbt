docker run --rm -v $(pwd):/src debian:11 \
         /bin/sh -c "apt-get update; \
         apt-get install -y gcc python3 python3-build \
            python3-pip python3-venv flex make \
            texinfo unzip help2man gawk libtool-bin libncurses5-dev \
            bison wget rsync ;
         cd /src; \
         python3 -m build"
