# -*- mode: ruby -*-
# vi: set ft=ruby :

# All Vagrant configuration is done below. The "2" in Vagrant.configure
# configures the configuration version (we support older styles for
# backwards compatibility). Please don't change it unless you know what
# you're doing.
Vagrant.configure(2) do |config|

  config.vm.box = "ubuntu/trusty64"

  config.vm.define "single" do |vm|
    config.vm.network "forwarded_port", guest: 80, host: 8080
    config.vm.network "forwarded_port", guest: 443, host: 8888
  end

  # if using docker, use a base image with sshd and remove default box config
  config.vm.provider "docker" do |d, override|
    d.image="ubuntu_with_ssh:14.04"
    d.has_ssh=true
    override.vm.box=nil
  end

  # if using virtualbox, run on two vcpus
  config.vm.provider "virtualbox" do |v|
    v.cpus = 2
  end

  # Enable provisioning with Ansible.
  config.vm.provision "ansible" do |ansible|
    ansible.playbook = "ansible/playbook.yml"
    ansible.groups = {
      "www" => ["www","single"],
      "worker" => ["worker","single"],
      "all_groups:children" => ["www", "worker"]
    }
    ansible.verbose='vv'
  end

end
