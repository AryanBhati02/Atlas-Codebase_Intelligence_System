## TO-DOs for mee

- Restore `tsc -b &&` in package.json build script and change few things i have left laterr 


data for current fps i got while testng after the change
Visible nodes       FPS still       FPS moving       Frametime
 7(clusters only)     144             144              7ms
      68            143–144         143–144            7ms                      
      163             120             120~             8ms     
     ~643              96            40–66           13–25ms
     ~996            15–46           15–40           25–66ms
   ~1,200            10–40           10–28           25–100ms
   ~1,400             2–20            4–10           50–500ms
    1,400+             1–4            1–4             250ms+ 


## Performance spike i got while testing everything both 3d and 2d section area 

- 2D smooth zone: ≤ 200 visible nodes (≥120 fps)
- 2D broken zone: ≥ 1,000 visible nodes (<10 fps)
- 3D smooth zone: ≤ 113 visible nodes (≥130 fps)  
- 3D broken zone: ≥ 210 visible nodes (18–72 fps fluctuating)
- Memory is NOT a bottleneck at any tested size (heap stayed under 50MB)
- 144 fps ceiling = monitor refresh rate, not actual GPU limit in my testing sometime the fps jump above 150 

## Target 1

Keep visible-node-count under 200 at all times via clustering + sub-clustering
in both 2D and 3D views. Above 200 visible nodes, automatically aggregate into
cluster nodes. Apply thingto 3D rendering.