import subprocess
import time
import struct
import os,sys
sys.path.append('%s/data/python' % os.environ['ANTELOPE'])
from antelope.datascope import closing, dbopen
from antelope.stock import str2epoch, epoch2str
from numpy import *
from matplotlib import pyplot as plt
from array import array #This is for fast io when writing binary 
from collections import defaultdict

#Read ASCII arrival time file output by FMM code

def num(s):
#Convert a string to a number, choosing int or float automatically
# SLOW, don't use for large lists
    try:
        return int(s)
    except ValueError:
        return float(s)

def load_faults():
#Load the california fault map
    fnam='cal_faults.dat'
    fid=open(fnam,'r')
    a=fid.readlines()
    faultlon=[];faultlat=[]
    for line in a:
        tmp=line.strip().split()
        if isnan(num(tmp[0])):
            faultlon.append(nan)
            faultlat.append(nan)
        else:
            faultlon.append(num(tmp[0]))
            faultlat.append(num(tmp[1]))
    print 'Faults loaded...'
    return faultlon,faultlat

def read_arrtimes(fnam='arrtimes.dat',ifplot=0): #default name
#Read arrival times from file fnam
    print 'Reading arrival times from '+fnam
    #Open and read header
    fid = open(fnam,'r')
    tmp=fid.readline().strip().split()
    nz=num(tmp[0]);nlat=num(tmp[1]);nlon=num(tmp[2]) #Number of grid points
    tmp=fid.readline().strip().split()
    dz=num(tmp[0]);dlat=num(tmp[1]);dlon=num(tmp[2]) #Spacing of grid points
    tmp=fid.readline().strip().split()
    oz=num(tmp[0]);olat=num(tmp[1]);olon=num(tmp[2]) #Origin of grid points
    tmp=fid.readline().strip().split()
    poo=num(tmp[0])                         #number of sets of arrival times
    tmp=fid.readline().strip().split()
    poo=num(tmp[0])                         #source and path for arrival time ??? 
    print 'poop'

    #Now read the traveltimes and sort into a matrix
    data=empty((nlat,nlon,nz))
    for ix in range(nlon):
        for iy in range(nlat):
            for iz in range(nz):
                tmp=float(fid.readline().strip())
                data[iy,ix,iz]=tmp
    fid.close()

    #Create vectors of geographic coordinates
    elon=olon+(dlon*nlon);
    elat=olat+(dlat*nlat);
    lonvec=linspace(olon,elon,nlon);
    latvec=linspace(olat,elat,nlat);

    #Now plot
    if ifplot: #adhoc
        flon,flat=load_faults()
        plt.figure(figsize=(6,6))
        plt.plot(flon,flat,'k')
        plt.axis([-118,-115,32,35])
        plt.pcolor(lonvec,latvec,data[:,:,6])
    return data

def find_containing_cube(px,py,pz,xvec,yvec,zvec):
#Find the 8 endpoints for the cell which contains point px,py
#  We take advantage of the regular grid
#  Assumes the point is inside the volume defined by xvec,yvec,zvec
#  Returns an array of size 8,3 where the rows contain x,y,z coordinates of the cubes endpoints
#  Also returns indexes of endpoints
    #Find the nearest node point and indexes <--"indices" sounds stupid to me
    xind,xnode=find_nearest(px,xvec)
    yind,ynode=find_nearest(py,yvec)
    zind,znode=find_nearest(pz,zvec)
    #Now check if the 3 coordinates of p are greater or less than the node it is nearest
    if px>=xnode: #px is east of the nearest node
        xi=xind+1
        xn=xvec[xi]
    else:        #px is west of the nearest node
        xi=xind-1
        xn=xvec[xi]
    if py>=ynode: #px is north of the nearest node
        yi=yind+1
        yn=yvec[yi]
    else:        #px is south of the nearest node
        yi=yind-1
        yn=yvec[yi]
    if pz>=znode: #px is above the nearest node
        zi=zind+1
        zn=zvec[zi]
    else:        #px is below the nearest node
        zi=zind-1
        zn=zvec[zi]
    #Add new endpoints to define the cube
    endpoints=[]
    endpoints.append( [xnode,ynode,znode] )
    endpoints.append( [xn,ynode,znode] )
    endpoints.append( [xn,yn,znode]    )
    endpoints.append( [xnode,yn,znode] )
    endpoints.append( [xnode,ynode,zn] )
    endpoints.append( [xn,ynode,zn] )
    endpoints.append( [xn,yn,zn]    )
    endpoints.append( [xnode,yn,zn] )
    #Add indices
    indexes=[]
    indexes.append( [xind,yind,zind] )
    indexes.append( [xi,yind,zind] )
    indexes.append( [xi,yi,zind]    )
    indexes.append( [xind,yi,zind] )
    indexes.append( [xind,yind,zi] )
    indexes.append( [xi,yind,zi] )
    indexes.append( [xi,yi,zi]    )
    indexes.append( [xind,yi,zi] )

    return endpoints,indexes

def find_nearest(px,xvec):
#Find the nearest x in xvec 
#  returns index
    best_ind=0
    shortest=100000000.0;
    for ii in range(len(xvec)):
        if abs(xvec[ii]-px)<shortest:
            shortest=abs(xvec[ii]-px)
            best_ind=ii
    return best_ind,xvec[best_ind]

def read_binary_float(fid,n=0,precision='double'):
#read the nth float value from a binary file at the with the given precision
# following python conventions, 0 is the index of the first value
    if precision is 'single':
        numbytes=4;packstr='f'
    else:
        numbytes=8;packstr='d'
    offset=n*numbytes #Go to the right spot in the file
    fid.seek(offset)
    raw=fid.read(numbytes)
    tmp=struct.unpack(packstr,raw)
    val=tmp[0]
    return val

def grid_search_traveltimes_rms(arrsta,qx,qy,qz,arrvec,li):
#Find the minimum value of some criterion by performing a grid search
# We aren't necessarily searching the whole grid; we may be skipping values
#   sta         list of station names; strings
#   qx,qy,qz    vectors of indices to search through
#   arrvec      vector of arrivals in the same order as sta
#   li          Linear_index class for the entire traveltime grid
    from numpy import array #There is no reason this should be here, but the next line generated error messages if it wasn't. I'm confused
    rms=array([])
    search_inds=Linear_index(len(qx),len(qy),len(qz))
    for ix in qx:  #Loop over the three vectors, searching every point
        for iy in qy:
            for iz in qz:
                calctt=array([]); #initialize the calculated tt vector
                ind=li.get_1D(ix,iy,iz) #Find the vector index
                for sta in arrsta: #Build vector of calculated ttimes
                    #print 'bin.'+sta+'.traveltime'
                    fid = open('bin.'+sta+'.traveltime')
                    calctt=append(calctt, read_binary_float(fid,ind) )
                    #print read_binary_float(fid,ind)
                    fid.close()
                rms=append(rms, sqrt(mean( (arrvec-calctt)**2 )) ) #Root-mean-square, yo
    #Now find the 3D index of the best point so far
    min_ind=rms.argmin()
    (minx,miny,minz)=search_inds.get_3D(min_ind)
    minx=qx[minx]; miny=qy[miny]; minz=qz[minz];
    return minx,miny,minz

def grid_search_traveltimes_origin(arrsta,qx,qy,qz,arrvec,li):
#Find the minimum value of the origin time standard deviation following Ben-Zion et al., 1992 (JGR)
#  sta          list of station names; strings
#   qx,qy,qz    vectors of indices to search through
#   arrvec      vector of absolute arrivals in the same order as sta
#   li          Linear_index class for the entire traveltime grid
    from numpy import array #There is no reason this should be here, but the next line generated error messages if it wasn't. I'm confused
    rms=array([])
    origin_std=array([])
    search_inds=Linear_index(len(qx),len(qy),len(qz))
    for ix in qx:  #Loop over the three vectors, searching every point
        for iy in qy:
            for iz in qz:
                calctt=array([]); #initialize the calculated tt vector
                ind=li.get_1D(ix,iy,iz) #Find the vector index
                for sta in arrsta: #Build vector of calculated ttimes
                    #print 'bin.'+sta+'.traveltime'
                    fid = open('bin.'+sta+'.traveltime')
                    calctt=append(calctt, read_binary_float(fid,ind) )
                    #print read_binary_float(fid,ind)
                    fid.close()
                orivec=arrvec-calctt
                origin_std=append(origin_std, orivec.std() )
    #Now find the 3D index of the best point so far
    min_ind=origin_std.argmin()
    (minx,miny,minz)=search_inds.get_3D(min_ind)
    minx=qx[minx]; miny=qy[miny]; minz=qz[minz];
    return minx,miny,minz,origin_std.min()

def fix_boundary_search(qx,nx):
#When performing a grid search on a subgrid, make sure you don't go off the edges
#  qx         search vectors, these will be modified then returned
#  nx         max index [li.nx]
    for ix in range(len(qx)):
        if qx[ix]<0:
            qx[ix]=0
        if qx[ix]>nx:
            qx[ix]=nx
    newqx=uniq(qx)
    return newqx

def uniq(input):
#Remove duplicate items from a list. Preserves order.
  output = []
  for x in input:
    if x not in output:
      output.append(x)
  return output

class Linear_index():
    #A class which can quickly convert 3D indices to a single vector index
    def __init__(self,nx,ny,nz):
        #We are using the FMM fast order which is x, y, z (lon,lat,depth)
        self.nx=nx; self.ny=ny; self.nz=nz

    def get_1D(self,ix,iy,iz):
        #Convert 3 indices to a single vector index
        #CAREFUL WITH PYTHON INDEXING
        iv = ix*self.ny*self.nz + iy*self.nz + iz #Check on this
        return iv

    def get_3D(self,iv):
        #Convert the vector index into 3 matrix indices
        ix= iv/(self.ny*self.nz)
        iy=(iv%(self.ny*self.nz))/self.nz
        iz=iv-ix*self.ny*self.nz-iy*self.nz
        return ix,iy,iz

class Parameters():
#The basic parameters of the velocity and interface grids and whatnot
    def __init__(self):
        #Velocity grid
        self.vel_minlon=     -118.007
        self.vel_dlon=       0.0109
        self.vel_nlon=       273
        self.vel_minlat=     32.4613
        self.vel_dlat=       0.0091
        self.vel_nlat=       252
        self.vel_minr=       6325.0
        self.vel_dr=         1.0
        self.vel_nr=         51
        #derived
        self.vel_dlon_rad=  self.vel_dlon*pi/180.0 #These are the actual values in vgrids.in
        self.vel_dlat_rad=  self.vel_dlat*pi/180.0

        #Propagation grid !!!Later, I'll derive all these from the values for the velocity grid above
        self.prop_minlon=        -117.95
        self.prop_minlat=        32.5
        self.prop_minz=          0.0
        self.prop_nlon=          250
        self.prop_nlat=          230
        self.prop_nr=            46
        #derived
        self.prop_dlon=          self.vel_dlon
        self.prop_dlat=          self.vel_dlat
        self.prop_dr=            self.vel_dr
        #Build vectors of the grid axes. These loops are more accurate than linspace somehow
        self.prop_lonvec=[]
        self.prop_latvec=[]
        self.prop_rvec=[]
        for ii in range(self.prop_nlon):
            self.prop_lonvec.append( self.vel_minlon+self.vel_dlon*ii )
        for ii in range(self.prop_nlat):
            self.prop_latvec.append( self.vel_minlat+self.vel_dlat*ii )
        for ii in range(self.prop_nr):
            self.prop_rvec.append(   self.vel_minr+self.vel_dr*ii     )
#self.prop_rvec=linspace(self.vel_minr,self.vel_minr+(self.vel_dr*self.vel_nr),self.vel_nr)

class Station():
    """
    A container class to hold station metadata.
    """
    def __init__(self, name, lat, lon, elev):
        self.name, self.lat, self.lon, self.elev = name, lat, lon, elev

    def __str__(self):
        ret = 'Station Object\n--------------\n'
        ret += 'name:\t\t%s\n' % self.name
        ret += 'lat: \t\t%f\n' % self.lat
        ret += 'lon: \t\t%f\n' % self.lon
        ret += 'elev: \t\t%f\n' % self.elev

    def show(self): #show the contents of the class
        print '%s %5.4f %5.4f %5.2f'% (self.name,self.lon,self.lat,self.elev)

class StationList(list):
    """
    A container class for a list of Station objects.

    This class replaces the deprecated Stalist class.
    """
    def __init__(self, inp, is_db=True):
        if is_db: self._init_db(inp)
        else: self._init_scedc(inp)

    def __str__(self):
        ret = 'StationList Object\n------------------\n'
        for sta in self:
            ret += 'sta:\t\t%s\n' % sta.name
            ret += 'lat:\t\t%f\n' % sta.lat
            ret += 'lon:\t\t%f\n' % sta.lon
            ret += 'elev:\t\t%f\n' % sta.elev
        return ret

    def _init_db(self, db):
        """
        Initialize station list using a CSS3.0 database as input.
        """
        with closing(dbopen(db, 'r')) as db:
            tbl_site = db.schema_tables['site']
            tbl_site = tbl_site.sort('sta', unique=True)
            for record in tbl_site.iter_record():
                sta, lat, lon, elev = record.getv('sta', 'lat', 'lon', 'elev')
                self.append(Station(sta, lat, lon, elev))

    def _init_scedc(self, infile):
        """
        Initialize station list using SCEDC format flat file as input.
        """
        infile = open(infile, 'r')
        for line in infile:
            line = line.strip().split() #stripping may be uneccessary
            self.append(Station(line[0],
                                 float(line[1]),
                                 float(line[2]),
                                 float(line[3])))

class _Event():
    """
    A container class for earthquake event metadata.
    """
    #def __init__(self, time, lat, lon, depth, mag, magtype=None, evid=None):
    def __init__(self, *args, **kwargs):
        """
        Initialize Event object using one of two possible inputs.

        This first (standard) input method is to simply supply a 
        CSS3.0 database path and an evid.

        The second method requires an auxiliary read function which will parse
        an input flat file (probably SCEDC format) and pass the following
        arguments in the following order.
        EG. event = Event(time,
                          latitude,
                          longitude,
                          depth,
                          magnitude,
                          phase_list,
                          magtype=magnitude_type,
                          evid=event_id)
        The keyword arguments (magtype and evid) are optional.
        """
        if len(args) == 2: self._init_from_db(*args)
        else: self._init_from_aux(*args, **kwargs)

    def __str__(self):
        ret = 'Event Object\n------------\n'
        ret += 'evid:\t\t%d\n' % self.evid
        ret += 'time:\t\t%f\n' % self.time
        ret += 'lat:\t\t%f\n' % self.lat
        ret += 'lon:\t\t%f\n' % self.lon
        ret += 'depth:\t\t%f\n' % self.depth
        ret += 'mag:\t\t%f\n' % self.mag
        ret += 'magtype:\t%s\n' % self.magtype
        ret += 'year:\t\t%d\n' % self.year
        ret += 'month:\t\t%d\n' % self.month
        ret += 'day:\t\t%d\n' % self.day
        ret += 'hour:\t\t%d\n' % self.hour
        ret += 'minute:\t\t%d\n' % self.minute
        ret += 'second:\t\t%d\n' % self.second
        ret += 'arrivals:\n'
        if len(self.arrivals) == 0:
            ret += '\t\tNone\n'
        else:
            for i in range(len(self.arrivals)):
                for line in  ('%s' % self.arrivals[i]).split('\n'):
                    ret += '\t\t%s\n' % line
        return ret

    def _init_from_db(self, db, evid):
        """
        Initialize Event object using a CSS3.0 database as input.
        """
        if evid == None: raise(Exception('No \'evid\' supplied. Could not '
            'initialize Event object from CSS3.0 database.'))
        with closing(dbopen(db, 'r')) as db:
            view = db.schema_tables['event']
            view = view.join('origin')
            view = view.subset('evid == %s' % evid)
            view = view.subset('orid == prefor')
            #If for some reason this subset is empty, just take the first
            #solution as preferred. EG. prefor field is unitialized.
            if view.record_count == 0:
                view = db.schema_tables['origin']
                view = db.schema_tables['event']
                view = view.join('origin')
                view = view.subset('evid == %s' % evid)
            view = view.join('netmag', outer=True)
            view.record = 0
            evid, time, lat, lon, depth, mag, magtype =  view.getv('evid',
                'time', 'lat', 'lon', 'depth', 'magnitude', 'magtype')
            self.evid       = evid
            self.time       = time
            self.lat        = lat
            self.lon        = lon
            self.depth      = depth
            self.mag        = mag
            self.magtype    = magtype
            self.year       = int(epoch2str(time, '%Y'))
            self.month      = int(epoch2str(time, '%m'))
            self.day        = int(epoch2str(time, '%d'))
            self.hour       = int(epoch2str(time, '%H'))
            self.minute     = int(epoch2str(time, '%M'))
            self.second     = float(epoch2str(time, '%S.%s'))
            view = view.join('assoc')
            view = view.join('arrival')
            arrivals = [ record.getv('sta',
                                     'arrival.time',
                                     'phase') \
                                     + (None, ) \
                                     for record in view.iter_record()
                       ]
            self.arrivals = [ Phase(sta, time, phase, qual)
                            for sta, time, phase, qual in arrivals
                            ]

    def _init_from_aux(self, time, lat, lon, dpeth, mag, magtype=None, evid=None):
        """
        Initialize Event object using an auxiliary read function.

        Auxiliary read function must parse flat file and pass parameters 
        to Event contsructor.
        """
        self.time = time
        self.lat        = lat
        self.lon        = lon
        self.depth      = depth
        self.mag        = mag
        self.magtype    = magtype
        self.year = int(epoch2str(time, '%Y'))
        self.month = int(epoch2str(time, '%m'))
        self.day = int(epoch2str(time, '%d'))
        self.hour = int(epoch2str(time, '%H'))
        self.minute = int(epoch2str(time, '%M'))
        self.second = float(epoch2str(time, '%S.%s'))
        self.arrivals = phase_list

class Phase():
    """
    A container class for phase data.
    """
    def __init__(self, sta, time, phase, qual):
        self.sta = sta
        self.time = time
        self.phase = phase
        self.qual = qual

    def __str__(self):
        ret = 'Arrival Object\n--------------\n'
        ret += 'sta:\t\t%s\n' % self.sta
        ret += 'time:\t\t%f\n' % self.time
        ret += 'phase:\t\t%s\n' % self.phase
        ret += 'qual:\t\t%s\n'  % self.qual
        return ret

class Traveltime_header_file():
#This reads the header file passed as an argument by fnam, saves all of the header info to a class
    def __init__(self,fnam):
       fid = open(fnam,'r')
       tmp=fid.readline().strip().split()
       self.nz=num(tmp[0]);self.nlat=num(tmp[1]);self.nlon=num(tmp[2]) #Number of grid points
       tmp=fid.readline().strip().split()
       self.dz=num(tmp[0]);self.dlat=num(tmp[1]);self.dlon=num(tmp[2]) #Spacing of grid points
       tmp=fid.readline().strip().split()
       self.oz=num(tmp[0]);self.olat=num(tmp[1]);self.olon=num(tmp[2]) #Origin of grid points
       tmp=fid.readline().strip().split()
       self.arrsets=num(tmp[0])                         #number of sets of arrival times
       tmp=fid.readline().strip().split()
       self.srcpath=num(tmp[0])                         #source and path for arrival time ???
       fid.close()

def process_events(dbin, dbout, events, station_list, params):
    from run_3D_loc import run_3d_location_algorithm
    for event in events:
        event = _Event(dbin, event)
        solution = run_3d_location_algorithm(event, station_list, params)

