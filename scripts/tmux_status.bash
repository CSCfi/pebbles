#!/bin/bash
tmux start-server\; has-session -t status 2>/dev/null

if [ "$?" -eq 1 ]; then
  cd /home/cloud-user

  # Run pre command.
  

  # Create the session and the first window.
  TMUX= tmux new-session -d -s status -n server


  # Create other windows.
  tmux new-window -c /home/cloud-user -t status:1 -n api
  tmux new-window -c /home/cloud-user -t status:2 -n worker
  tmux new-window -c /home/cloud-user -t status:3 -n frontend


  # Window "server"
  
  tmux send-keys -t status:0.0 '' C-m
  tmux send-keys -t status:0.0 top\ -c C-m

  tmux splitw -t status:0
  tmux select-layout -t status:0 even-vertical
  
  tmux send-keys -t status:0.1 '' C-m
  tmux send-keys -t status:0.1 watch\ -n\ 10\ df\ -h C-m

  tmux splitw -t status:0
  tmux select-layout -t status:0 even-vertical
  
  tmux send-keys -t status:0.2 '' C-m
  tmux send-keys -t status:0.2 dstat\ -tsmcpyf\ 60 C-m

  tmux splitw -t status:0
  tmux select-layout -t status:0 even-vertical
  
  tmux send-keys -t status:0.3 '' C-m
  tmux send-keys -t status:0.3 dstat\ -tndrf\ --socket\ 60 C-m

  tmux select-layout -t status:0 even-vertical

  tmux select-pane -t status:0.0

  # Window "api"
  
  tmux send-keys -t status:1.0 '' C-m
  tmux send-keys -t status:1.0 ssh\ api\ tail\ -F\ /webapps/pouta_blueprints/logs/gunicorn\*.log C-m

  tmux select-layout -t status:1 even-vertical

  tmux select-pane -t status:1.0

  # Window "worker"
  
  tmux send-keys -t status:2.0 '' C-m
  tmux send-keys -t status:2.0 ssh\ worker\ tail\ -F\ /webapps/pouta_blueprints/logs/celery.log C-m

  tmux splitw -t status:2
  tmux select-layout -t status:2 even-vertical
  
  tmux send-keys -t status:2.1 '' C-m
  tmux send-keys -t status:2.1 ssh\ worker\ tail\ -F\ /webapps/pouta_blueprints/logs/celery-system.log C-m

  tmux splitw -t status:2
  tmux select-layout -t status:2 even-vertical
  
  tmux send-keys -t status:2.2 '' C-m
  tmux send-keys -t status:2.2 ssh\ -t\ worker\ watch\ -n\ 5\ \'\"python\ -m\ json.tool\ /var/spool/pb_instances/docker_driver.json\ \|\ egrep\ \\\"state\|docker_url\|num\|lifetime\|error_count\\\"\ \|\ xargs\ -n14\"\' C-m

  tmux select-layout -t status:2 even-vertical

  tmux select-pane -t status:2.0

  # Window "frontend"
  
  tmux send-keys -t status:3.0 '' C-m
  tmux send-keys -t status:3.0 ssh\ frontend\ tail\ -F\ /webapps/pouta_blueprints/logs/nginx\*.log C-m

  tmux splitw -t status:3
  tmux select-layout -t status:3 even-vertical
  
  tmux send-keys -t status:3.1 '' C-m
  tmux send-keys -t status:3.1 ssh\ frontend\ tail\ -F\ /webapps/pouta_blueprints/logs/celery\*.log C-m

  tmux splitw -t status:3
  tmux select-layout -t status:3 even-vertical
  
  tmux send-keys -t status:3.2 '' C-m
  tmux send-keys -t status:3.2 ssh\ frontend\ -t\ watch\ -d\ \'echo\ \"number\ of\ proxy\ routes\"\;\ grep\ location\ /webapps/pouta_blueprints/run/proxy_conf.d/proxy.conf\ \|\ wc\ -l\' C-m

  tmux select-layout -t status:3 even-vertical

  tmux select-pane -t status:3.0

  tmux select-window -t 0
fi

if [ -z "$TMUX" ]; then
  tmux -u attach-session -t status
else
  tmux -u switch-client -t status
fi
