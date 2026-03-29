Installation
----------------------------------------------

sudo -i

git clone https://github.com/ai-tinker/filemon /opt/filemon

cd /opt/filemon

cp .env.example .env
nano .env # complete with correct information
cp filemon.logrotate /etc/logrotate.d/filemon
cp filemon.service /etc/systemd/system/

mkdir /var/lib/filemon

# Install pip and venv 
sudo apt install python3-pip python3-venv -y
python3 -m venv venv
chmod 600 /opt/filemon/checkedfile.conf

sudo systemctl daemon-reload
sudo systemctl enable filemon
sudo systemctl stop filemon
sudo systemctl start filemon

sudo systemctl status filemon
