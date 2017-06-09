#!/bin/sh

if [ "$(whoami)" != "root" ] ; then
	echo "Please run this script with root access !"
	exit 1
fi

if [ -e /usr/bin/yum ] ; then
	i="yum -y install"
else
	i="apt-get install -f"
fi

echo "Installing python 3 and libssl"
$i python3 python3-pip libssl-dev

if [ -e /usr/bin/pip3 ] ; then
	p=pip3
else
	p=python3-pip
fi

function osinstall {
	echo -n "Trying to install $1 using OS package manager..."
	$p python3-numpy &> /dev/null
	if [ $? -ne 0 ] ; then
		$i numpy
	fi
}

osinstall numpy
osinstall scipy
$p install -r requirements.txt
