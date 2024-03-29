#    This file is based on the file 'example.py' of iSpec.
#    Copyright Sergi Blanco-Cuaresma - http://www.blancocuaresma.com/s/

import os
import sys
import numpy as np
import pandas as pd
import logging
import multiprocessing
from multiprocessing import Pool
from scipy.interpolate import interpn

#--- iSpec directory -------------------------------------------------------------

#if we're in the ispec directory
ispec_dir = os.getcwd() + '/' 

# #if we're not in the ispec directory we should specify its path, for example:
# #making it a requested argument
# ispec_dir = sys.argv[1] #if we use this method we should change lines 51, 52 and 53

# testing in the last meeting:
# sys.path.insert(0, "/home/sousasag/Programas/GIT_projects/Others/iSpec")
# ispec_dir = '/home/sousasag/Programas/GIT_projects/Others/iSpec/'


sys.path.insert(0, os.path.abspath(ispec_dir))
print(ispec_dir)
import ispec

"""
Defining arguments that will be necessary in the functions' inputs:

    Input_file (has to either be in this directory or express the full path):
    - star: name of the star
    - star_file: name of the fits file containing the spectrum of the star
    (star_file should include the path if it is not in the same directory as this script)
    - snr: signal-to-noise ratio 
    - resolution: Resolution characteristic of the spectograph used
    - teff: temperature of the star
    - logg: surface gravity
    - vmic: microturbulence
    - MH: metalicity
    
    
    line_list: number of the Reduced_line_list (1 or 2) - str
    
    code: which code we wish to use (turbospectrum, synthe or moog) - str
"""

input_file = sys.argv[1]
line_list = sys.argv[2]
code = sys.argv[3]

starter_df = pd.read_csv(input_file, names=['star', 'star_file', 'snr', 'resolution', 'teff', 'logg', 'vmic', 'MH'])

star_name = starter_df['star'][0]
star_file = starter_df['star_file'][0]
snr = starter_df['snr'][0]
initial_teff = starter_df['teff'][0]
initial_logg = starter_df['logg'][0]
initial_vmic = starter_df['vmic'][0]
initial_MH = starter_df['MH'][0]
initial_R = starter_df['resolution'][0]


"""
This is Pedro Branco's code to calculate the limb darkening coefficent
"""

Tabela1=pd.read_csv("values_limbo.csv") #the file has to be in the same directory
Temperature=np.arange(3500,7000,100)
Logg=np.arange(3.0,5.0,0.1)
FeH=np.arange(-0.5,0.6,0.1)
Variables=(Temperature,Logg,FeH)
Values_limbo=np.array(Tabela1["Limbo"])

VL=np.zeros((len(Temperature),len(Logg),len(FeH)))
zz=0

for i in range(len(Temperature)):
    for j in range(len(Logg)):
        for k in range(len(FeH)):
            VL[i][j,k]=Values_limbo[zz]
            zz+=1

def interpolation_function(T,logg,feh):
    """
    This function calculates the limb darkening coefficient using interpolation
    The ranges of values that the imput parameters use are:
    -T: Range=[3500.0,7000.0]
    -logg: Range=[3,5]
    -feh: Range=[-0.5,0.5]
    """
    Temperature=np.arange(3500,7000,100)
    Logg=np.arange(3.0,5.0,0.1)
    FeH=np.arange(-0.5,0.6,0.1)
    
    if T < 3500 or T > Temperature[-1]:
        return 0.6
    if logg < 3 or logg > Logg[-1]:
        return 0.6
    if feh < -0.5 or feh > FeH[-1]:
        return 0.6
    
    return interpn(Variables, VL,np.array([T,logg,feh]))[0]


###############################################################################

#--- Change LOG level ----------------------------------------------------------
#LOG_LEVEL = "warning"
LOG_LEVEL = "info"
logger = logging.getLogger() # root logger, common for all
logger.setLevel(logging.getLevelName(LOG_LEVEL.upper()))
################################################################################

def cut_spectrum_from_range(star_spectrum, lower_lim=470, upper_lim=680):
    
    #--- Cut -----------------------------------------------------------------------
    logging.info("Cutting...")

    # - Keep points between two given wavelengths
    wfilter = ispec.create_wavelength_filter(star_spectrum, wave_base=lower_lim, wave_top=upper_lim)
    cutted_star_spectrum = star_spectrum[wfilter]
    
    return cutted_star_spectrum

def estimate_snr_from_flux(star_spectrum):
    
    #--- Estimate SNR from flux ----------------------------------------------------
    logging.info("Estimating SNR from fluxes...")
    num_points = 10
    estimated_snr = ispec.estimate_snr(star_spectrum['flux'], num_points=num_points)
    
    return estimated_snr

def add_noise_to_spectrum(star_spectrum, snr):
    """
    Add noise to a spectrum (ideally to a synthetic one) based on a given SNR.
    """

    distribution = "poisson" # "gaussian"
    noisy_star_spectrum = ispec.add_noise(star_spectrum, snr, distribution)
    
    return noisy_star_spectrum

def continuum_fit(star_spectrum):

    #--- Continuum fit -------------------------------------------------------------
    model = "Splines" # "Polynomy"
    degree = 2
    nknots = None # Automatic: 1 spline every 5 nm
    from_resolution = None #added by me

    # Strategy: Filter first median values and secondly MAXIMUMs in order to find the continuum
    order='median+max'
    median_wave_range=0.05
    max_wave_range = 4.0 #changed by me

    star_continuum_model = ispec.fit_continuum(star_spectrum, from_resolution=from_resolution,                                 nknots=nknots, degree=degree,                                 median_wave_range=median_wave_range,                                 max_wave_range=max_wave_range,                                 model=model, order=order,                                 automatic_strong_line_detection=True,                                 strong_line_probability=0.5,                                 use_errors_for_fitting=True)
    
def determine_radial_velocity_with_mask(mu_cas_spectrum):

    #--- Radial Velocity determination with linelist mask --------------------------
    logging.info("Radial velocity determination with linelist mask...")
    # - Read atomic data
    mask_file = ispec_dir + "input/linelists/CCF/Narval.Sun.370_1048nm/mask.lst"
    
    ccf_mask = ispec.read_cross_correlation_mask(mask_file)

    models, ccf = ispec.cross_correlate_with_mask(mu_cas_spectrum, ccf_mask,                             lower_velocity_limit=-200, upper_velocity_limit=200,                             velocity_step=1.0, mask_depth=0.01,                             fourier=False)

    # Number of models represent the number of components
    components = len(models)
    # First component:
    rv = np.round(models[0].mu(), 2) # km/s
    rv_err = np.round(models[0].emu(), 2) # km/s
    
    return rv, rv_err

def correct_radial_velocity(mu_cas_spectrum, rv):

    #--- Radial Velocity correction ------------------------------------------------
    logging.info("Radial velocity correction...")

    mu_cas_spectrum = ispec.correct_velocity(mu_cas_spectrum, rv)
    
    return mu_cas_spectrum

def normalizing(star_file, snr, lower_lim=470, upper_lim=680):

    star_spectrum = ispec.read_spectrum(star_file)
    
    star_spectrum = cut_spectrum_from_range(star_spectrum, lower_lim, upper_lim)
    estimated_snr = estimate_snr_from_flux(star_spectrum)
    star_spectrum = add_noise_to_spectrum(star_spectrum, snr)
    
    #--- Continuum fit -------------------------------------------------------------
    model = "Splines" # "Polynomy"
    degree = 2
    nknots = None # Automatic: 1 spline every 5 nm
    from_resolution = None #added by me

    # Strategy: Filter first median values and secondly MAXIMUMs in order to find the continuum
    order='median+max'
    median_wave_range=0.05
    max_wave_range = 4.0 #changed by me

    star_continuum_model = ispec.fit_continuum(star_spectrum, from_resolution=from_resolution,                                 nknots=nknots, degree=degree,                                 median_wave_range=median_wave_range,                                 max_wave_range=max_wave_range,                                 model=model, order=order,                                 automatic_strong_line_detection=True,                                 strong_line_probability=0.5,                                 use_errors_for_fitting=True)
    
    #--- Normalize -------------------------------------------------------------
    continuum_error = True
    #continuum_error = False 
    normalized_star_spectrum = ispec.normalize_spectrum(star_spectrum, star_continuum_model, consider_continuum_errors=continuum_error)
    
    rv, rv_err = determine_radial_velocity_with_mask(normalized_star_spectrum)
    
    star_spectrum = correct_radial_velocity(normalized_star_spectrum, rv)

    ##--- Save spectrum ------------------------------------------------------------
    logging.info("Saving spectrum...")
    
    normed_star_file = star_file[:-5] + '_normed.fits'
    
    ispec.write_spectrum(star_spectrum, normed_star_file)
        
    return normed_star_file, star_spectrum, estimated_snr, rv, rv_err

def determine_astrophysical_parameters_using_synth_spectra(normed_star_file, code, line_list, star_name, initial_teff, initial_logg, initial_MH, initial_vmic, initial_R):

    #they are the same:
    star_spectrum = ispec.read_spectrum(normed_star_file) 
    normalized_star_spectrum = ispec.read_spectrum(normed_star_file) 

     # Use a fixed value because the spectrum is already normalized
    star_continuum_model = ispec.fit_continuum(star_spectrum, fixed_value=1.0, model="Fixed value")
    
    #--- Model spectra ----------------------------------------------------------
    
    # Parameters
    initial_alpha =  -0.27*initial_MH + 0.05 #added
    initial_vmac = ispec.estimate_vmac(initial_teff, initial_logg, initial_MH)
    initial_vsini = 2.0
    initial_limb_darkening_coeff = interpolation_function(initial_teff,initial_logg,initial_MH)
    initial_vrad = 0
    max_iterations = 6

    # Selected model amtosphere, linelist and solar abundances
    model = ispec_dir + "/input/atmospheres/MARCS.GES/"

    atomic_linelist_file = ispec_dir + "/input/linelists/transitions/GESv6_atom_hfs_iso.420_920nm/atomic_lines.tsv"

    if "ATLAS" in model:
        solar_abundances_file = ispec_dir + "/input/abundances/Grevesse.1998/stdatom.dat"
    else:
        # MARCS
        solar_abundances_file = ispec_dir + "/input/abundances/Grevesse.2007/stdatom.dat"

    isotope_file = ispec_dir + "/input/isotopes/SPECTRUM.lst"

    # Load chemical information and linelist
    atomic_linelist = ispec.read_atomic_linelist(atomic_linelist_file, wave_base=np.min(star_spectrum['waveobs']), wave_top=np.max(star_spectrum['waveobs']))
    atomic_linelist = atomic_linelist[atomic_linelist['theoretical_depth'] >= 0.01] # Select lines that have some minimal contribution in the sun

    isotopes = ispec.read_isotope_data(isotope_file)


    # Load model atmospheres
    modeled_layers_pack = ispec.load_modeled_layers_pack(model)

    # Load SPECTRUM abundances
    solar_abundances = ispec.read_solar_abundances(solar_abundances_file)

    # Free parameters
    free_params = ["vsini"]

    # Free individual element abundance
    free_abundances = None
    linelist_free_loggf = None

    # Line regions
    line_regions = ispec.read_line_regions(ispec_dir + 'Reduced_line_list_{}.txt'.format(line_list))

    # Read segments if we have them or...
    segments = ispec.read_segment_regions(ispec_dir + "/input/regions/fe_lines_segments.txt")

    obs_spec, modeled_synth_spectrum, params, errors, abundances_found, loggf_found, status, stats_linemasks =             ispec.model_spectrum(normalized_star_spectrum, star_continuum_model,             modeled_layers_pack, atomic_linelist, isotopes, solar_abundances, free_abundances, linelist_free_loggf, initial_teff,             initial_logg, initial_MH, initial_alpha, initial_vmic, initial_vmac, initial_vsini,             initial_limb_darkening_coeff, initial_R, initial_vrad, free_params, segments=segments,             linemasks=line_regions,             enhance_abundances=True,             use_errors = True,             vmic_from_empirical_relation = False,             vmac_from_empirical_relation = True,             max_iterations=max_iterations,             tmp_dir = None,             code=code)
    
    ##--- Save results -------------------------------------------------------------
    logging.info("Saving results...")
    d_params = {'teff': [params['teff']], 'logg': [params['logg']], 'MH': [params['MH']], 'alpha': [params['alpha']], 
           'vmic': [params['vmic']], 'vmac': [params['vmac']], 'vsini': [params['vsini']], 
           'limb_darkening_coeff': [params['limb_darkening_coeff']], 'R': [params['R']]} 
    df_params = pd.DataFrame(d_params)
    df_params.to_csv('./{}_params_{}_{}.txt'.format(star_name, code, line_list), index=None)
    
    d_errors = {'teff': [errors['teff']], 'logg': [errors['logg']], 'MH': [errors['MH']], 'alpha': [errors['alpha']], 
           'vmic': [errors['vmic']], 'vmac': [errors['vmac']], 'vsini': [errors['vsini']], 
           'limb_darkening_coeff': [errors['limb_darkening_coeff']], 'R': [errors['R']]} 
    df_errors = pd.DataFrame(d_errors)
    df_errors.to_csv('./{}_errors_{}_{}.txt'.format(star_name, code, line_list), index=None)
    
    
    logging.info("Saving synthetic spectrum...")
    
    synth_filename = normed_star_file[:-11] + "{}_{}.fits".format(code, line_list)
    ispec.write_spectrum(modeled_synth_spectrum, synth_filename)
    
    return params['vsini'], errors['vsini']



normed_star_file, star_spectrum, estimated_snr, rv, rv_err = normalizing(star_file, snr, lower_lim=470, upper_lim=680)

vsini, err_vsini = determine_astrophysical_parameters_using_synth_spectra(normed_star_file, code, line_list, star_name, initial_teff, initial_logg, initial_MH, initial_vmic, initial_R)

print('vsini = {} +/- {}'.format(vsini, err_vsini))

