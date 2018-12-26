source ~/env/py3/http/bin/activate
nohup python nest_sim.py >api.log 2>&1 &
nohup python app.py >http.log 2>&1 &
