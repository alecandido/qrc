python3 run/lab.py 
                 | lines 
                 | last 
                 | tee { open $"($in)/0-probe.json" 
                         | get program 
                         | print $"\nprogram:\n\n($in)" 
                        } 
                 | rm -rf $in
