# UCEclima Lambda 9.2.0 · © 2026 Diego Quishpe Landeta, Teresa Palacios y María Eugenia Ávila-Salem · CC BY-NC 4.0 (ver LICENSE)
"""Mismo paso hidráulico del prototipo, con bucles compilados para mallas grandes."""
import numpy as np
from numba import njit


@njit(cache=True)
def hydraulic_step(z,active,n,h,available,qx,qy,hmax,vmax,duration,dt,dx,dy,g,eps,free,lib_o,lib_e,lib_n,lib_s):
    ny,nx=z.shape
    scale=np.ones_like(h)
    limited=0
    for r in range(ny):
        for c in range(1,nx):
            if not(active[r,c-1] and active[r,c]):
                qx[r,c]=0
                continue
            eta0=z[r,c-1]+h[r,c-1];eta1=z[r,c]+h[r,c]
            depth=max(eta0,eta1)-max(z[r,c-1],z[r,c])
            if depth<=eps:
                qx[r,c]=0
            else:
                old=qx[r,c];rough=(n[r,c-1]+n[r,c])/2
                qx[r,c]=(old-g*depth*dt*(eta1-eta0)/dx)/(1+g*dt*rough**2*abs(old)/depth**(7/3))
    for r in range(1,ny):
        for c in range(nx):
            if not(active[r-1,c] and active[r,c]):
                qy[r,c]=0
                continue
            eta0=z[r-1,c]+h[r-1,c];eta1=z[r,c]+h[r,c]
            depth=max(eta0,eta1)-max(z[r-1,c],z[r,c])
            if depth<=eps:
                qy[r,c]=0
            else:
                old=qy[r,c];rough=(n[r-1,c]+n[r,c])/2
                qy[r,c]=(old-g*depth*dt*(eta1-eta0)/dy)/(1+g*dt*rough**2*abs(old)/depth**(7/3))
    for r in range(ny):
        qx[r,0]=0;qx[r,nx]=0
        if free:                                          # G22: solo en los tramos de borde declarados libres
            if active[r,0] and lib_o[r]:qx[r,0]=-h[r,0]*np.sqrt(g*h[r,0])
            if active[r,nx-1] and lib_e[r]:qx[r,nx]=h[r,nx-1]*np.sqrt(g*h[r,nx-1])
    for c in range(nx):
        qy[0,c]=0;qy[ny,c]=0
        if free:
            if active[0,c] and lib_n[c]:qy[0,c]=-h[0,c]*np.sqrt(g*h[0,c])
            if active[ny-1,c] and lib_s[c]:qy[ny,c]=h[ny-1,c]*np.sqrt(g*h[ny-1,c])
    for r in range(ny):
        for c in range(nx):
            outgoing=(max(qx[r,c+1],0)+max(-qx[r,c],0))*dy+\
                     (max(qy[r+1,c],0)+max(-qy[r,c],0))*dx
            if outgoing>0:
                scale[r,c]=min(available[r,c]*dx*dy/(dt*outgoing),1.)
                if active[r,c] and scale[r,c]<1-1e-12:limited+=1
    for r in range(ny):
        for c in range(1,nx):
            qx[r,c]*=scale[r,c-1] if qx[r,c]>=0 else scale[r,c]
        qx[r,0]*=scale[r,0];qx[r,nx]*=scale[r,nx-1]
    for r in range(1,ny):
        for c in range(nx):
            qy[r,c]*=scale[r-1,c] if qy[r,c]>=0 else scale[r,c]
    for c in range(nx):
        qy[0,c]*=scale[0,c];qy[ny,c]*=scale[ny-1,c]
    correction=0.;min_h=1e10
    for r in range(ny):
        for c in range(nx):
            new=available[r,c]+dt*((qx[r,c]-qx[r,c+1])/dx+(qy[r,c]-qy[r+1,c])/dy)
            min_h=min(min_h,new)
            if new<0:correction+=-new*dx*dy
            h[r,c]=max(new,0.) if active[r,c] else 0.
            hmax[r,c]=max(hmax[r,c],h[r,c])
            if h[r,c]>=.05:  # G17 (Delta): v = q/h solo con h >= 5 cm
                vx=(qx[r,c]+qx[r,c+1])/2/h[r,c]
                vy=(qy[r,c]+qy[r+1,c])/2/h[r,c]
                vmax[r,c]=max(vmax[r,c],np.sqrt(vx*vx+vy*vy))
            if h[r,c]>=.3:duration[r,c]+=dt
    outflow=dt*(dy*(qx[:,-1].sum()-qx[:,0].sum())+dx*(qy[-1,:].sum()-qy[0,:].sum()))
    return outflow,correction,limited,min_h
