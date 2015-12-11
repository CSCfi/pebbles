# -*- mode: ruby -*-
# vi: set ft=ruby :

# All Vagrant configuration is done below. The "2" in Vagrant.configure
# configures the configuration version (we support older styles for
# backwards compatibility). Please don't change it unless you know what
# you're doing.
Vagrant.configure(2) do |config|

  config.vm.box = "ubuntu/trusty64"

  config.vm.define "single", autostart: true do |vm|
    config.vm.network "forwarded_port", guest: 80, host: 8080
    config.vm.network "forwarded_port", guest: 443, host: 8888
    config.vm.synced_folder ".", "/shared_folder"
  end

  # if using virtualbox, run on two vcpus
  config.vm.provider "virtualbox" do |v|
    v.cpus = 2
    v.memory = 1024
  end

  # if using docker, use a base image with sshd and remove default box config
  config.vm.provider "docker" do |d, override|
    d.image="ubuntu_with_ssh:14.04"
    d.has_ssh=true
    override.vm.box=nil
  end

 # mimic multi container deployment. In a single deployment mode www services are accessible on localhost
  config.vm.provision "shell",
    inline: "echo '127.0.0.1 api' | sudo tee -a /etc/hosts",
    privileged: false

  config.vm.provision "shell",
    inline: "echo '127.0.0.1 db' | sudo tee -a /etc/hosts",
    privileged: false

  config.vm.provision "shell",
    inline: "echo '127.0.0.1 redis' | sudo tee -a /etc/hosts",
    privileged: false


  # Enable provisioning with Ansible.
  config.vm.provision "ansible" do |ansible|
    ansible.playbook = "ansible/playbook.yml"
    ansible.groups = {
      "api" => ["api","single"],
      "worker" => ["worker","single"],
      "frontend" => ["frontend", "single"],
      "all_groups:children" => ["api", "worker", "frontend"]
    }
    ansible.verbose='vv'
  end

  # history initialization for easy tmux access
  # note on privileged: see https://github.com/mitchellh/vagrant/issues/1673
  config.vm.provision "shell",
    inline: "echo 'sudo tmux -f /shared_folder/tmux.conf att' > /home/vagrant/.bash_history",
    privileged: false

end
