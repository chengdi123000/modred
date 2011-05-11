from modaldecomp import ModalDecomp
import util
import numpy as N
import util 

class BPOD(ModalDecomp):
    """
    Balanced Proper Orthogonal Decomposition
    
    Generate direct and adjoint modes from direct and adjoint simulation 
    snapshots. BPOD inherits from ModalDecomp and uses it for low level
    functions.
    
    """
    
    def __init__(self, load_field=None, save_field=None, save_mat=util.\
        save_mat_text, load_mat=util.load_mat_text, inner_product=None,
        maxFieldsPerNode=None, numNodes=1, directSnapPaths=None, 
        adjointSnapPaths=None, LSingVecs=None, singVals=None, RSingVecs=None, 
        hankelMat=None, verbose=True):
        """
        BPOD constructor
        
        load_field - Function to load a snapshot given a filepath.
        save_field - Function to save a mode given data and an output path.
        save_mat - Function to save a matrix.
        inner_product - Function to take inner product of two snapshots.
        directSnapPaths - List of filepaths from which direct snapshots can be
            loaded.
        adjointSnapPaths - List of filepaths from which direct snapshots can be
            loaded.
        SVD of hankelMat gives:
        LSingVecs * singVals * RSingVecs* = hankelMat = "Y* X"
        hankelMat is adjoint modes "multiplied by" direct modes.
        """
        # Base class constructor defines common data members
        ModalDecomp.__init__(self, load_field=load_field, save_field=save_field,
            save_mat=save_mat, inner_product=inner_product, maxFieldsPerNode=\
            maxFieldsPerNode, numNodes=numNodes, verbose=verbose)

        # Additional data members
        self.directSnapPaths = directSnapPaths
        self.adjointSnapPaths = adjointSnapPaths
        
        # Data members that will be set after computation
        self.LSingVecs = LSingVecs
        self.singVals = singVals
        self.RSingVecs = RSingVecs
        self.hankelMat = hankelMat
        self.load_mat = load_mat
        
    def load_decomp(self, hankelMatPath, LSingVecsPath, singValsPath, 
        RSingVecsPath, load_mat=None):
        """
        Loads the decomposition matrices from file. 
        """
        if load_mat is not None:
            self.load_mat = load_mat
        if self.load_mat is None:
            raise UndefinedError('Must specify a load_mat function')
        if self.mpi.isRankZero():
            self.LSingVecs = self.load_mat(LSingVecsPath)
            self.singVals = N.squeeze(N.array(self.load_mat(singValsPath)))
            self.RSingVecs = self.load_mat(RSingVecsPath)
        else:
            self.LSingVecs = None
            self.singVals = None
            self.RSingVecs = None
        if self.mpi.parallel:
            self.LSingVecs = self.mpi.comm.bcast(self.LSingVecs, root=0)
            self.singVals = self.mpi.comm.bcast(self.singVals, root=0)
            self.RSingVecs = self.mpi.comm.bcast(self.LSingVecs, root=0)
    
    def save_decomp(self, hankelMatPath, LSingVecsPath, singValsPath, 
        RSingVecsPath):
        """Save the decomposition matrices to file."""
        if self.save_mat is None and self.mpi.isRankZero():
            raise util.UndefinedError('save_mat is undefined, cant save')
            
        if self.mpi.isRankZero():
            if hankelMatPath is not None:
                self.save_mat(self.hankelMat, hankelMatPath)
            if LSingVecsPath is not None:
                self.save_mat(self.LSingVecs, LSingVecsPath)
            if RSingVecsPath is not None:
                self.save_mat(self.RSingVecs, RSingVecsPath)
            if singValsPath is not None:
                self.save_mat(self.singVals, singValsPath)
        
    def compute_decomp(self, hankelMatPath='hankelMat.txt', LSingVecsPath=\
        'LSingVecs.txt', singValsPath='singVals.txt', RSingVecsPath=\
        'RSingVecs.txt', directSnapPaths=None, adjointSnapPaths=None):
        """
        Compute BPOD decomposition, forms the Hankel matrix and its SVD
        
        LSingVecsPath - Output path for matrix of left singular vectors from 
            Hankel matrix SVD.
        singValsPath - Output path for singular values from Hankel matrix SVD.
        RSingVecsPath - Output path for matrix of right singular vectors from
            Hankel matrix SVD.
        """
        
        if directSnapPaths is not None:
            self.directSnapPaths = directSnapPaths
        if adjointSnapPaths is not None:
            self.adjointSnapPaths = adjointSnapPaths

        if self.directSnapPaths is None:
            raise util.UndefinedError('directSnapPaths is not given')
        if self.adjointSnapPaths is None:
            raise util.UndefinedError('adjointSnapPaths is not given')
            
        self.hankelMat = self.compute_inner_product_matrix(self.\
            adjointSnapPaths, self.directSnapPaths)

        if self.mpi.isRankZero():
            self.LSingVecs, self.singVals, self.RSingVecs = util.svd(self.\
                hankelMat)
        else:
            self.LSingVecs = None
            self.RSingVecs = None
            self.singVals = None
        if self.mpi.isParallel():
            self.LSingVecs = self.mpi.comm.bcast(self.LSingVecs, root=0)
            self.singVals = self.mpi.comm.bcast(self.singVals, root=0)
            self.RSingVecs = self.mpi.comm.bcast(self.RSingVecs, root=0)
           
        self.save_decomp(hankelMatPath, LSingVecsPath, singValsPath, 
            RSingVecsPath)
        
        #self.mpi.evaluate_and_bcast([self.LSingVecs,self.singVals,self.RSingVecs],\
        #  util.svd, arguments = [self.hankelMat])

    def compute_direct_modes(self, modeNumList, modePath, indexFrom=1,
        directSnapPaths=None):
        """
        Computes the direct modes and saves them to file.
        
        modeNumList - mode numbers to compute on this processor. This 
          includes the indexFrom, so if indexFrom=1, examples are:
          [1,2,3,4,5] or [3,1,6,8]. The mode numbers need not be sorted,
          and sorting does not increase efficiency. 
          Repeated mode numbers is not guaranteed to work. 
        modePath - Full path to mode location, e.g /home/user/mode_%d.txt.
        indexFrom - Choose to index modes starting from 0, 1, or other.
        self.RSingVecs, self.singVals must exist or an UndefinedError.
        """
        if self.RSingVecs is None:
            raise util.UndefinedError('Must define self.RSingVecs')
        if self.singVals is None:
            raise util.UndefinedError('Must define self.singVals')
            
        if directSnapPaths is not None:
            self.directSnapPaths = directSnapPaths
        
        buildCoeffMat = N.mat(self.RSingVecs) * N.mat(N.diag(self.singVals **\
            -0.5))

        self._compute_modes(modeNumList, modePath, self.directSnapPaths, 
            buildCoeffMat, indexFrom=indexFrom)
    
    def compute_adjoint_modes(self, modeNumList, modePath, indexFrom=1,
        adjointSnapPaths=None):
        """
        Computes the adjoint modes and saves them to file.
        
        modeNumList - mode numbers to compute on this processor. This 
          includes the indexFrom, so if indexFrom=1, examples are:
          [1,2,3,4,5] or [3,1,6,8]. The mode numbers need not be sorted,
          and sorting does not increase efficiency. 
          Repeated mode numbers is not guaranteed to work. 
        modePath - Full path to mode location, e.g /home/user/mode_%d.txt.
        indexFrom - Choose to index modes starting from 0, 1, or other.
        self.LSingVecs, self.singVals must exist or an UndefinedError.
        """
        if self.LSingVecs is None:
            raise UndefinedError('Must define self.LSingVecs')
        if self.singVals is None:
            raise UndefinedError('Must define self.singVals')
        if adjointSnapPaths is not None:
            self.adjointSnapPaths=adjointSnapPaths
        self.singVals = N.squeeze(N.array(self.singVals))
        
        buildCoeffMat = N.mat(self.LSingVecs) * N.mat(N.diag(self.singVals **\
            -0.5))
                 
        self._compute_modes(modeNumList, modePath, self.adjointSnapPaths,
            buildCoeffMat, indexFrom=indexFrom)
    
