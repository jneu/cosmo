#! /usr/bin/env python

from __future__ import print_function, absolute_import, division

'''
This ia a program designed to calibrate COS rawfiles to create CSUMs.

It also sets permissions and group ids appropriately as well
as zipping up any unzipped files to save space.
'''

__author__ = "Jo Taylor"
__date__ = "04-13-2016"
__maintainer__ = "Jo Taylor"

# Import necessary packages.
import sys
import datetime
import os
import glob
import shutil
import gzip
from astropy.io import fits as pf
import calcos
import smtplib
import multiprocessing as mp
import psutil
import argparse
import math
import time
import pdb
import numpy as np
import stat
import subprocess
from functools import partial
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from .ProgramGroups import *
from .dec_calcos import clobber_calcos_csumgz
from .hack_chmod import chmod
from .retrieval_info import BASE_DIR, CACHE

LINEOUT = "#"*75+"\n"
STAROUT = "*"*75+"\n"
PERM_755 = stat.S_IRWXU | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH
PERM_872 = stat.S_ISVTX | stat.S_IRUSR | stat.S_IXUSR | stat.S_IRGRP | stat.S_IXGRP

#------------------------------------------------------------------------------#
#------------------------------------------------------------------------------#

def timefunc(func):
    '''
    Decorator to time functions. 
    '''

    def wrapper(*args, **kw):
        t1 = datetime.datetime.now()
        result = func(*args, **kw)
        t2 = datetime.datetime.now()

        print("{0} executed in {1}".format(func.__name__, t2-t1))
        
        return result
    return wrapper

#------------------------------------------------------------------------------#
#------------------------------------------------------------------------------#

#@log_function
def unzip_mistakes(zipped):
    '''
    Occasionally, files will get zipped without having csums made.
    This function checks if each raw* file has a csum: if it does
    not, it unzips the file to be calibrated in the make_csum()
    function.

    Parameters:
    -----------
        zipped : list
            A list of all files in the base directory that are zipped

    Returns:
    --------
        Nothing
    '''

    if isinstance(zipped, str):
        zipped = [zipped]
    for zfile in zipped:
        rootname = os.path.basename(zfile)[:9]
        dirname = os.path.dirname(zfile)
        calibrate, badness= csum_existence(zfile)
        if badness is True:
            print("="*72 + "\n" + "="*72)
            print("The file is empty or corrupt: {0}".format(item))
            print("Deleting file")
            print("="*72 + "\n" + "="*72)
            os.remove(item)
            continue
        if calibrate is True:
            #chmod_recurs(dirname, PERM_755)
            files_to_unzip = glob.glob(zfile)
            uncompress_files(files_to_unzip)

#------------------------------------------------------------------------------#
#------------------------------------------------------------------------------#

def needs_processing(zipped):
    if isinstance(zipped, str):
        zipped = [zipped]
    files_to_calibrate = []
    for zfile in zipped:
        rootname = os.path.basename(zfile)[:9]
        dirname = os.path.dirname(zfile)
        calibrate, badness= csum_existence(zfile)
        if badness is True:
            print("="*72 + "\n" + "="*72)
            print("The file is empty or corrupt: {0}".format(item))
            print("Deleting file")
            print("="*72 + "\n" + "="*72)
            os.remove(item)
            continue
        if calibrate is True:
            files_to_calibrate.append(zfile)

    return files_to_calibrate

#------------------------------------------------------------------------------#
#------------------------------------------------------------------------------#

#@log_function
def make_csum(unzipped_raws):
    '''
    Calibrate raw files to produce csum files.

    Parameters:
    -----------
        unzipped_raws : list or string
            A list or string filenames that are unzipped to be calibrated.

    Returns:
    --------
        Nothing
    '''

    run_calcos = clobber_calcos_csumgz(calcos.calcos)
    #logger.info("Creating CSUM files")
    if isinstance(unzipped_raws, str):
        unzipped_raws = [unzipped_raws]
    for item in unzipped_raws:
#        calibrate, badness = csum_existence(item)
#        if badness:
#            print("="*72 + "\n" + "="*72)
#            print("The file is empty or corrupt: {0}".format(item))
#            print("Deleting file")
#            print("="*72 + "\n" + "="*72)
#            os.remove(item)
#            continue
#        if calibrate is True:
        dirname = os.path.dirname(item)
        outdirec = os.path.join(dirname, "tmp_out")
#        os.chmod(dirname, PERM_755)
#        os.chmod(item, PERM_755)
        try:
            run_calcos(item, outdir=outdirec, verbosity=2,
                       create_csum_image=True, only_csum=True,
                       compress_csum=False)
        except Exception as e:
            if type(e).__name__ == "IOError" and \
               e.args[0] == "Empty or corrupt FITS file":
                print("="*72 + "\n" + "="*72)
                print("The file is empty or corrupt: {0}".format(item))
                print("Deleting file")
                print("="*72 + "\n" + "="*72)
                os.remove(item)
                pass
            else:
                print(e)
            #logger.exception("There was an error processing {}:".format(item))
                pass
        csums = glob.glob(os.path.join(outdir, "*csum*"))
        if csums:
            for csum in csums:
                shutil.move(csum, dirname)
        shutil.rmtree(outdirec)

#------------------------------------------------------------------------------#
#------------------------------------------------------------------------------#

#@log_function
@timefunc
def chgrp(mydir):
    '''
    Walk through all directories in base directory and change the group ids
    to reflect the type of COS data (calbration, GTO, or GO).
    Group ids can be found by using the grp module, e.g.
    > grp.getgrnam("STSCI\cosstis").gr_gid
    User ids can be found using the pwd module e.g.
    > pwd.getpwnam("jotaylor").pw_uid

    Parameters:
    -----------
        mydir : string
            The base directory to walk through.

    Returns:
    --------
        Nothing
    '''
    
    user_id = 5026 # jotaylor's user ID
    for root, dirs, files in os.walk(mydir):
        # This expects the dirtree to be in the format /blah/blah/blah/12345
        pid = root.split("/")[-1]
        try:
            pid = int(pid)
        except ValueError:
            continue
        try:
            if pid in smov_proposals or pid in calib_proposals:
                grp_id = 6045 # gid for STSCI/cosstis group
            elif pid in gto_proposals:
                grp_id = 65546 # gid for STSCI/cosgto group
            else:
                grp_id = 65545 # gid for STSCI/cosgo group
            os.chown(root, user_id, grp_id)
        except PermissionError as e:
            print(repr(e))

            for filename in files:
                try:
                    os.chown(os.path.join(root, filename), user_id, grp_id)
                except PermissionError as e:
                    nothing = True
                    print(repr(e))
#------------------------------------------------------------------------------#
#------------------------------------------------------------------------------#

#@log_function
def chmod_recurs(dirname, perm):
    '''
    Edit permissions on a directory and all files in that directory.

    Parameters:
        dirname : string
            A string of the directory name to edit.
        perm : int (octal)
            An integer corresponding to the permission bit settings.

    Returns:
        Nothing
    '''

    #[os.chmod(os.path.join(root, filename)) for root,dirs,files in os.walk(DIRECTORY) for filename in files]
    # The above line works fine, but is confusing to read, and is only
    # marginally faster than than an explicit for loop.
    for root, dirs, files in os.walk(dirname):
        os.chmod(root, perm)
        if files:
            for item in files:
                os.chmod(os.path.join(root, item), perm)

#------------------------------------------------------------------------------#
#------------------------------------------------------------------------------#

def chmod_recurs_prl(perm, item):
    '''
    Edit permissions in parallel.
    
    Parameters:
        perm : int (octal)
            An integer corresponding to the permission bit settings.
        item : string
            A string of the directory/file name to edit.

    Returns:
        Nothing
    '''
    
    os.chmod(item, perm)

#------------------------------------------------------------------------------#
#------------------------------------------------------------------------------#

@timefunc
def chmod_recurs_sp(rootdir, perm):
    '''
    Edit permissions on a directory and all files in that directory.

    Parameters:
        perm : int (octal)
            An integer corresponding to the permission bit settings.
        rootdir : string
            A string of the directory name to edit.

    Returns:
        Nothing
    '''

    subprocess.check_call(["chmod", "-R", perm, rootdir])
     
#------------------------------------------------------------------------------#
#------------------------------------------------------------------------------#

#@log_function
def csum_existence(filename):
    '''
    Check for the existence of a CSUM for a given input dataset.

    Parameters:
    -----------
        filename : string
            A raw dataset name.

    Returns:
    --------
        calibrate : bool
            A boolean, True if the dataset should not be calibrated to create csums. 
        badness : bool
            A boolean, True if the dataset should be deleted (if corrupt or empty) 
    '''

    rootname = os.path.basename(filename)[:9]
    dirname = os.path.dirname(filename)
    # If getting one header keyword, getval is faster than opening.
    # The more you know.
    try:
        exptype = pf.getval(filename, "exptype")
    except KeyError:
#        exptype = None
        return False, False 
    except Exception as e:
        if type(e).__name__ == "IOError" and \
           e.args[0] == "Empty or corrupt FITS file":
            return False, True
    
    if exptype != "ACQ/PEAKD" and exptype != "ACQ/PEAKXD":
#    if exptype == "ACQ/IMAGE":
        csums = glob.glob(os.path.join(dirname,rootname+"*csum*"))
        if not csums:
            calibrate = True
        else:
            calibrate = True
    else:
        calibrate = False

    return calibrate, False

#------------------------------------------------------------------------------#
#------------------------------------------------------------------------------#

#@log_function
def compress_files(uz_files):
    '''
    Compress unzipped files and delete original unzipped files.

    Paramters:
    ----------
        uz_files : list or string
            Unzipped file(s) to zip

    Returns:
    --------
        Nothing
    '''

    if isinstance(uz_files, str):
        uz_files = [uz_files]
    for uz_item in uz_files:
        z_item = uz_item + ".gz"
        with open(uz_item, "rb") as f_in, gzip.open(z_item, "wb") as f_out:
            shutil.copyfileobj(f_in, f_out)
            print("Compressing {} -> {}".format(uz_item, z_item))
        if os.path.isfile(z_item):
            os.remove(uz_item)
        else:
            print("Something went terribly wrong zipping {}".format(uz_item))

#------------------------------------------------------------------------------#
#------------------------------------------------------------------------------#

#@log_function
def uncompress_files(z_files):
    '''
    Uncompress zipped files and delete original zipped files.

    Paramters:
    ----------
        z_files : list
            A list of zipped files to zip

    Returns:
    --------
        Nothing
    '''

    for z_item in z_files:
        uz_item = z_item.split(".gz")[0]
        with gzip.open(z_item, "rb") as f_in, open(uz_item, "wb") as f_out:
            shutil.copyfileobj(f_in, f_out)
            print("Uncompressing {} -> {}".format(z_item, uz_item))
        if os.path.isfile(uz_item):
            os.remove(z_item)
        else:
            print("Something went terribly wrong unzipping {}".format(z_item))

#------------------------------------------------------------------------------#
#------------------------------------------------------------------------------#

#@log_function
def send_email():
    '''
    Send a confirmation email. Currently not used.

    Parameters:
    -----------
        None

    Returns:
    --------
        Nothing
    '''

    msg = MIMEMultipart()
    msg["Subject"] = "Testing"
    msg["From"] = "jotaylor@stsci.edu"
    msg["To"] = "jotaylor@stsci.edu"
    msg.attach(MIMEText("Hello, the script is finished."))
    msg.attach(MIMEText("Testing line 2."))
    s = smtplib.SMTP("smtp.stsci.edu")
    s.sendmail("jotaylor@stsci.edu",["jotaylor@stsci.edu"], msg.as_string())
    s.quit()

#------------------------------------------------------------------------------#
#------------------------------------------------------------------------------#

@timefunc
def parallelize(func, iterable, funcargs=None, nprocs="check_usage"):
    from multiprocessing import Queue, Process

    if nprocs == "check_usage":
        playnice = False
        if playnice is True:
            core_frac = 0.25
        else:
            core_frac = 0.5 
        # Get load average of system and no. of hyper-threaded CPUs on current system.
        loadavg = os.getloadavg()[0]
        ncores = psutil.cpu_count()
        # If too many cores are being used, wait 10 mins, and reasses.
        while loadavg >= (ncores-1):
            print("Too many cores in usage, waiting 10 minutes before continuing...")
            time.sleep(600)
        else:
            avail = ncores - math.ceil(loadavg)
            nprocs = int(np.floor(avail * playmean))                       
        # If, after rounding, no cores are available, default to 1 to avoid
        # pooling with processes=0.
        if nprocs == 0:
            nprocs = 1

    out_q = Queue()
    chunksize = len(iterable)
    procs = []
    
    if funcargs is not None:
        if type(funcargs) is not tuple:
            print("ERROR: Arguments for function {} need to be tuple, exiting".
                  format(func))
            sys.exit()

    for i in range(nprocs):
        if type(iterable) is dict:
            subset = {k:iterable[k] for k in list(iterable.keys())[chunksize*i:chunksize*(i+1)]}
        else:
            subset = iterable[chunksize*i:chunksize*(i+1)]

        if funcargs is not None:
            inargs = (subset,) + funcargs + (out_q,)
        else:
            inargs = (subset, out_q)

        p = Process(target=func, args=inargs)                  
        procs.append(p)
        p.start()

    resultdict = {}
    for i in range(nprocs):
        resultdict.update(out_q.get())

    for p in procs:
        p.join()

    return resultdict

#------------------------------------------------------------------------------#
#------------------------------------------------------------------------------#

#@log_function
@timefunc
def parallelize2(myfunc, mylist, check_usage=False):
    '''
    Parallelize a function. Be a good samaritan and CHECK the current usage
    of resources before determining number of processes to use. If usage
    is too high, wait 10 minutes before checking again. Currently only
    supports usage with functions that act on a list. Will modify for
    future to support nargs.

    Parameters:
    -----------
        myfunc : function
            The function to be parallelized.
        mylist : list
            List to be used with function.

    Returns:
    --------
        Nothing
    '''

    # Percentage of cores to eat up.
    playnice = 0.25
    playmean = 0.40

    # Split list into multiple lists if it's large.
    maxnum = 25
    if len(mylist) > maxnum:
        metalist = [mylist[i:i+maxnum] for i in range(0, len(mylist), maxnum)]
    else:
        metalist = [mylist]
    for onelist in metalist:
        if check_usage:
            # Get load average of system and no. of hyper-threaded CPUs on current system.
            loadavg = os.getloadavg()[0]
            ncores = psutil.cpu_count()
            # If too many cores are being used, wait 10 mins, and reasses.
            while loadavg >= (ncores-1):
                print("Too many cores in usage, waiting 10 minutes before continuing...")
                time.sleep(600)
            else:
                avail = ncores - math.ceil(loadavg)
                nprocs = int(np.floor(avail * playmean))
            # If, after rounding, no cores are available, default to 1 to avoid
            # pooling with processes=0.
            if nprocs == 0:
                nprocs = 1
#            print("Using {0} cores at {1}".format(nprocs, datetime.datetime.now()))
        else:
            nprocs = 15
        pool = mp.Pool(processes=nprocs)
        pool.map(myfunc, onelist)
        pool.close()
        pool.join()

#------------------------------------------------------------------------------#
#------------------------------------------------------------------------------#

@timefunc
def check_disk_space():
    '''
    Determine how much free space there is in BASE_DIR

    Parameters:
    -----------
        None

    Returns:
    --------
#        free_gb : float
#            Number of free GB in BASE_DIR.
    '''
    
    statvfs = os.statvfs(BASE_DIR)
    free_gb = (statvfs.f_frsize * statvfs.f_bfree) / 1e9
    if free_gb < 200:
        print("WARNING: There are {0}GB left on disk".format(free_gb))
        unzipped_csums = glob.glob(os.path.join(BASE_DIR, "*", "*csum*.fits"))
        if not unzipped_csums:
            print("WARNING: Disk space is running very low, no csums to zip") 
        else:
            print("Zipping csums to save space...")
            if prl:
                parallelize(compress_files, unzipped_csums)
            else:
                compress_files(unzipped_csums)

#------------------------------------------------------------------------------#
#------------------------------------------------------------------------------#

def only_one_seg(uz_files):
    '''
    If rawtag_a and rawtag_b both exist in a list of raw files, 
    keep only one of the segments. Keep NUV and acq files as is.

    Parameters:
    -----------
        uz_files : list
            List of all unzipped files.

    Returns:
    --------
        uz_files_1seg : list
            List of all unzipped files with only one segment for a given root
            (if applicable).
    '''
    
    roots = [os.path.basename(x)[:9] for x in uz_files]
    uniqinds = []
    uniqroots = []
    for i in range(len(roots)):
        if roots[i] not in uniqroots:
            uniqroots.append(roots[i])
            uniqinds.append(i)
    uz_files_1seg = [uz_files[j] for j in uniqinds]
    
    return uz_files_1seg
    
#------------------------------------------------------------------------------#
#------------------------------------------------------------------------------#

def handle_nullfiles(nullfiles):
    '''
    It can be difficult to tell if all files found by find_new_cos_data with
    program ID 'NULL' are actually COS files (e.g. reference files that start
    with 'L' can accidentally be downloaded). Delete any files that are not
    actually COS files

    Parameters:
    -----------
        nullfiles : list
            List of all files in the NULL directory

    Returns:
    --------
        None
    '''

    for item in nullfiles:
        with pf.open(item) as hdulist:
            hdr0 = hdulist[0].header
        try:
            instrument = hdr0["instrume"]
            try:
                pid = hdr0["proposid"]
                if pid > 0:
                    pid = str(pid)
                    # These files have program IDs and should be moved.
                    if not os.path.exists(os.path.join(BASE_DIR, pid)):
                        os.mkdir(os.path.join(BASE_DIR, pid)) 
                    shutil.move(item, os.path.join(BASE_DIR, pid))
            except KeyError:
                try:
                    # These files are reference files and should be removed.
                    useafter = hdr0["useafter"]
                    os.remove(item)
                except KeyError:
                    os.remove(item)
        except KeyError:
            # These files are not COS datasets and should be removed.
            os.remove(item)

#------------------------------------------------------------------------------#
#------------------------------------------------------------------------------#

@timefunc
def work_laboriously(prl, do_chmod):
    '''
    Run all the functions in the correct order.

    Parameters:
    -----------
        prl : Boolean
            Switch for running functions in parallel

    Returns:
    --------
        Nothing
    '''

    # First, change permissions of the base directory so we can modify files.
    print("Beginning manualabor in {0} at {1}...\n".format(BASE_DIR, datetime.datetime.now()))
    if do_chmod: 
        print("Opening permissions of {0}..".format(BASE_DIR))
        chmod(BASE_DIR, PERM_755, None, True)

    # Delete any files with program ID = NULL that are not COS files.
    nullfiles = glob.glob(os.path.join(BASE_DIR, "NULL", "*fits*")) 
    if nullfiles:
        print("Handling {0} NULL datasets...".format(len(nullfiles)))
        handle_nullfiles(nullfiles) 
    
    # Get a list of all unzipped files and zip them.
    unzipped = glob.glob(os.path.join(BASE_DIR, "*", "*fits"))
    print("Zipping {0} unzipped file(s)...".format(len(unzipped)))
    if unzipped:
        if prl:
            parallelize(compress_files, unzipped)
        else:
            compress_files(unzipped)

    # When calibrating zipped raw files, you need to calibrate both segments 
    # separately since calcos can't find the original 
    zipped_raws = glob.glob(os.path.join(BASE_DIR, "*", "*rawtag*fits.gz")) + \
                       glob.glob(os.path.join(BASE_DIR, "*", "*rawacq.fits.gz"))

    to_calibrate = needs_processing(zipped_raws)    
    # Loop through files and calibrate in chunks of 300? to 
    # ensure that disk space is not filled. 
    max_files = 3000
    if to_calibrate:
        num_files = 0
        if len(to_calibrate) > max_files:
            while num_files < len(to_calibrate):
                print("There are {0} file(s) to calibrate, calibrating files {1}:{2}".format(len(to_calibrate), num_files, num_files+max_files))
                if prl:
                    parallelize(make_csum, to_calibrate[num_files:num_files+max_files])
                else:
                    make_csum(to_calibrate[num_files:num_files+max_files])
                num_files += max_files
        else:
            print("There are {0} file(s) to calibrate, calibrating all...".format(len(to_calibrate)))
            if prl:
                parallelize(make_csum, to_calibrate[num_files:])
            else:
                make_csum(to_calibrate[num_files:])

    # Check again for unzipped files.
    all_unzipped = glob.glob(os.path.join(BASE_DIR, "*", "*fits"))
    if all_unzipped:
        print("Zipping {0} uncompressed files...".format(len(all_unzipped)))
        if prl:
            parallelize(compress_files, all_unzipped)
        else:
            compress_files(all_unzipped)
        
    # Check for the temporary output directories used during calibration,
    # and delete if present. 
    tmp_dirs = glob.glob(os.path.join(BASE_DIR, "*", "tmp_out"))
    if tmp_dirs:
        for bad_dir in tmp_dirs:
            shutil.rmtree(bad_dir)

    # Change permissions back to protect data.
    print("Changing group permissions of {0}...".format(BASE_DIR))
    chgrp(BASE_DIR)
    if do_chmod:
        print("Closing permissions of {0}..".format(BASE_DIR))
        chmod(BASE_DIR, PERM_872, None, True)

    print("\nFinished at {0}.".format(datetime.datetime.now()))

#------------------------------------------------------------------------------#
#------------------------------------------------------------------------------#

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--prl", dest="prl", action="store_true",
                        default=False, help="Parallellize functions")
    parser.add_argument("--chmod", dest="do_chmod", action="store_false",
                        default=True, help="Switch to turn off chmod")
    args = parser.parse_args()

    work_laboriously(args.prl, args.do_chmod)
