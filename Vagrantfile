# -*- mode: ruby -*-
# vi: set ft=ruby :

# All Vagrant configuration is done below. The "2" in Vagrant.configure
# configures the configuration version (we support older styles for
# backwards compatibility). Please don't change it unless you know what
# you're doing.
Vagrant.configure(2) do |config|

  config.vm.box = "ubuntu/trusty64"

  # needed for parallel ansible
  config.ssh.insert_key = false

  # www host
  config.vm.define "www" do |www|

    www.vm.network "forwarded_port", guest: 80, host: 8080
    www.vm.network "forwarded_port", guest: 443, host: 8888
    www.vm.network "private_network", ip: "10.0.0.10"

    # Enable parallel provisioning with Ansible.
    config.vm.provision "ansible" do |ansible|
      ansible.playbook = "ansible/playbook.yml"
      ansible.limit = 'all'
      ansible.groups = {
        "www" => ["www"],
        "worker" => ["worker"],
        "all_groups:children" => ["www", "worker"]
      }
      ansible.verbose='vv'
    end

    www.vm.provider "docker" do |d|
      d.name="www"
    end

  end

  # worker node
  config.vm.define "worker" do |worker|
    # docker specific stuff
    worker.vm.provider "docker" do |d|
      d.link "www:www"
      d.name="worker"
    end

    worker.vm.network "private_network", ip: "10.0.0.11"
  end

  # if using docker, use a base image with sshd and remove default box config
  config.vm.provider "docker" do |d, override|
    d.image="ubuntu_with_ssh:14.04"
    d.has_ssh=true
    override.vm.box=nil
  end

end
