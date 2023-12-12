"""Contains the class and functions associated with computing the rotational strength for VCD calculations by finite difference at the Hartree-Fock level of theory."""

import psi4
import numpy as np
import math
from apyib.utils import run_psi4
from apyib.hamiltonian import Hamiltonian
from apyib.hf_wfn import hf_wfn
from apyib.finite_difference import finite_difference



# Computes the parity of a given list.
def perm_parity(a):
    parity = 1
    for i in range(0,len(a)-1):
        if a[i] != i:
            parity *= -1
            j = min(range(i,len(a)), key=a.__getitem__)
            a[i],a[j] = a[j],a[i]
    return parity

# Heap's algorithm for generating all the permutations of a given list.
def heaperm(a, size, b, p):
    if size == 1:
        b.append(a.copy())
        p.append(perm_parity(a.copy()))
        return
 
    for i in range(size):
        heaperm(a, size-1, b, p)
 
        if size & 1:
            a[0], a[size-1] = a[size-1], a[0]
        else:   
            a[i], a[size-1] = a[size-1], a[i]

# Computes the molecular orbital overlap between two wavefunctions.
def compute_mo_overlap(ndocc, nbf, bra_basis, bra_wfn, ket_basis, ket_wfn):
    mints = psi4.core.MintsHelper(bra_basis)

    if bra_basis == ket_basis:
        ao_overlap = mints.ao_overlap().np
    elif bra_basis != ket_basis:
        ao_overlap = mints.ao_overlap(bra_basis, ket_basis).np
            
    #print("AO Overlap:")
    #print(ao_overlap)
    #print("\n")

    mo_overlap = np.zeros_like(ao_overlap)
    mo_overlap = mo_overlap.astype('complex128')

    for m in range(0, nbf):
        for n in range(0, nbf):
            for mu in range(0, nbf):
                for nu in range(0, nbf):
                    mo_overlap[m, n] += np.conjugate(np.transpose(bra_wfn[mu, m])) *  ao_overlap[mu, nu] * ket_wfn[nu, n]
    return mo_overlap

# Compute MO-level phase correction.
def compute_phase(ndocc, nbf, unperturbed_basis, unperturbed_wfn, ket_basis, ket_wfn):
    # Compute MO overlaps.
    mo_overlap1 = compute_mo_overlap(ndocc, nbf, unperturbed_basis, unperturbed_wfn, ket_basis, ket_wfn)
    mo_overlap2 = np.conjugate(np.transpose(mo_overlap1))

    new_ket_wfn = np.zeros_like(ket_wfn)

    # Compute the phase corrected coefficients.
    for m in range(0, nbf):
        # Compute the normalization.
        N = np.sqrt(mo_overlap1[m][m] * mo_overlap2[m][m])

        # Compute phase factor.
        phase_factor = mo_overlap1[m][m] / N 

        # Compute phase corrected overlap.
        for mu in range(0, nbf):
            new_ket_wfn[mu][m] += ket_wfn[mu][m] * (phase_factor ** -1)

    return new_ket_wfn


# Computes the overlap between two Hartree-Fock wavefunctions.
def compute_hf_overlap(ndocc, mo_overlap):
    det = np.arange(0, ndocc)
    size = len(det)
    permutation = []
    parity = []

    heaperm(det, size, permutation, parity)
    num_perms = math.factorial(size)

    mo_prod = 1 
    hf_overlap = 0 
    for m in range(0, num_perms):
        for n in range(0, num_perms):
            sign = parity[m] * parity[n]
            for i in range(0, ndocc):
                mo_prod *= mo_overlap[permutation[m][i], permutation[n][i]]
            hf_overlap += 1/num_perms * sign * mo_prod
            mo_prod = 1 

    return hf_overlap



class AAT(object):
    """
    The atomic axial tensor object computed by finite difference.
    """
    def __init__(self, nbf, ndocc, unperturbed_wfn, unperturbed_basis, nuc_pos_wfn, nuc_neg_wfn, nuc_pos_basis, nuc_neg_basis, mag_pos_wfn, mag_neg_wfn, mag_pos_basis, mag_neg_basis, nuc_pert_strength, mag_pert_strength):

        # Basis sets and wavefunctions from calculations with respect to nuclear displacements.
        self.nuc_pos_basis = nuc_pos_basis
        self.nuc_neg_basis = nuc_neg_basis
        self.nuc_pos_wfn = nuc_pos_wfn
        self.nuc_neg_wfn = nuc_neg_wfn

        # Basis sets and wavefunctions from calculations with respect to magnetic field perturbations.
        self.mag_pos_basis = mag_pos_basis
        self.mag_neg_basis = mag_neg_basis
        self.mag_pos_wfn = mag_pos_wfn
        self.mag_neg_wfn = mag_neg_wfn

        # Components required for finite difference AATs.
        self.nuc_pert_strength = nuc_pert_strength
        self.mag_pert_strength = mag_pert_strength

        # Components required for permutations.
        self.nbf = nbf
        self.ndocc = ndocc

        # Components required for phase.
        self.unperturbed_basis = unperturbed_basis
        self.unperturbed_wfn = unperturbed_wfn

    # Computes the permutations required for the Hartree-Fock wavefunction.
    def compute_perms(self):
        det = np.arange(0, self.ndocc)
        size = len(det)
        permutation = []
        parity = []

        heaperm(det, size, permutation, parity)
        return parity, permutation

    # Computes the overlap between two Hartree-Fock wavefunctions.
    def compute_hf_overlap1(self, mo_overlap, parity, permutation):
        num_perms = len(permutation)
        mo_prod = 1
        hf_overlap = 0
        for n in range(0, num_perms):
            sign = parity[n]
            for i in range(0, self.ndocc):
                mo_prod *= mo_overlap[permutation[-1][i], permutation[n][i]]
            hf_overlap += sign * mo_prod
            mo_prod = 1

        return hf_overlap

    # Computes the Hartree-Fock AATs.
    def compute_aat(self, alpha, beta):
        # Compute phase corrected wavefunctions.
        pc_nuc_pos_wfn = compute_phase(self.ndocc, self.nbf, self.unperturbed_basis, self.unperturbed_wfn, self.nuc_pos_basis[alpha], self.nuc_pos_wfn[alpha])
        pc_nuc_neg_wfn = compute_phase(self.ndocc, self.nbf, self.unperturbed_basis, self.unperturbed_wfn, self.nuc_neg_basis[alpha], self.nuc_neg_wfn[alpha])
        pc_mag_pos_wfn = compute_phase(self.ndocc, self.nbf, self.unperturbed_basis, self.unperturbed_wfn, self.mag_pos_basis[beta], self.mag_pos_wfn[beta])
        pc_mag_neg_wfn = compute_phase(self.ndocc, self.nbf, self.unperturbed_basis, self.unperturbed_wfn, self.mag_neg_basis[beta], self.mag_neg_wfn[beta])

        # Compute molecular orbital overlaps with phase correction applied.
        mo_overlap_pp = compute_mo_overlap(self.ndocc, self.nbf, self.nuc_pos_basis[alpha], pc_nuc_pos_wfn , self.mag_pos_basis[beta], pc_mag_pos_wfn)
        mo_overlap_np = compute_mo_overlap(self.ndocc, self.nbf, self.nuc_neg_basis[alpha], pc_nuc_neg_wfn , self.mag_pos_basis[beta], pc_mag_pos_wfn)
        mo_overlap_pn = compute_mo_overlap(self.ndocc, self.nbf, self.nuc_pos_basis[alpha], pc_nuc_pos_wfn , self.mag_neg_basis[beta], pc_mag_neg_wfn)
        mo_overlap_nn = compute_mo_overlap(self.ndocc, self.nbf, self.nuc_neg_basis[alpha], pc_nuc_neg_wfn , self.mag_neg_basis[beta], pc_mag_neg_wfn)

        
        # Compute Hartree-Fock overlaps.
        hf_pp = compute_hf_overlap(self.ndocc, mo_overlap_pp)
        hf_np = compute_hf_overlap(self.ndocc, mo_overlap_np)
        hf_pn = compute_hf_overlap(self.ndocc, mo_overlap_pn)
        hf_nn = compute_hf_overlap(self.ndocc, mo_overlap_nn)
        #print(hf_pp)
        #print(hf_np)
        #print(hf_pn)
        #print(hf_nn)

        # Compute the AAT.
        I = (1 / (2 * self.nuc_pert_strength * self.mag_pert_strength)) * (hf_pp - hf_np - hf_pn + hf_nn)

        return I

    # Computes the Hartree-Fock AATs.
    def compute_aat1(self, alpha, beta):
        # Compute phase corrected wavefunctions.
        pc_nuc_pos_wfn = compute_phase(self.ndocc, self.nbf, self.unperturbed_basis, self.unperturbed_wfn, self.nuc_pos_basis[alpha], self.nuc_pos_wfn[alpha])
        pc_nuc_neg_wfn = compute_phase(self.ndocc, self.nbf, self.unperturbed_basis, self.unperturbed_wfn, self.nuc_neg_basis[alpha], self.nuc_neg_wfn[alpha])
        pc_mag_pos_wfn = compute_phase(self.ndocc, self.nbf, self.unperturbed_basis, self.unperturbed_wfn, self.mag_pos_basis[beta], self.mag_pos_wfn[beta])
        pc_mag_neg_wfn = compute_phase(self.ndocc, self.nbf, self.unperturbed_basis, self.unperturbed_wfn, self.mag_neg_basis[beta], self.mag_neg_wfn[beta])

        # Compute molecular orbital overlaps with phase correction applied.
        mo_overlap_pp = compute_mo_overlap(self.ndocc, self.nbf, self.nuc_pos_basis[alpha], pc_nuc_pos_wfn , self.mag_pos_basis[beta], pc_mag_pos_wfn)
        mo_overlap_np = compute_mo_overlap(self.ndocc, self.nbf, self.nuc_neg_basis[alpha], pc_nuc_neg_wfn , self.mag_pos_basis[beta], pc_mag_pos_wfn)
        mo_overlap_pn = compute_mo_overlap(self.ndocc, self.nbf, self.nuc_pos_basis[alpha], pc_nuc_pos_wfn , self.mag_neg_basis[beta], pc_mag_neg_wfn)
        mo_overlap_nn = compute_mo_overlap(self.ndocc, self.nbf, self.nuc_neg_basis[alpha], pc_nuc_neg_wfn , self.mag_neg_basis[beta], pc_mag_neg_wfn)

        # Compute permutations.
        parity, perms = self.compute_perms()
    
        # Compute Hartree-Fock overlaps.
        hf_pp = self.compute_hf_overlap1(mo_overlap_pp, parity, perms)
        hf_np = self.compute_hf_overlap1(mo_overlap_np, parity, perms)
        hf_pn = self.compute_hf_overlap1(mo_overlap_pn, parity, perms)
        hf_nn = self.compute_hf_overlap1(mo_overlap_nn, parity, perms)
        #print(hf_pp)
        #print(hf_np)
        #print(hf_pn)
        #print(hf_nn)

        # Compute the AAT.
        I = (1 / (2 * self.nuc_pert_strength * self.mag_pert_strength)) * (hf_pp - hf_np - hf_pn + hf_nn)

        return I









