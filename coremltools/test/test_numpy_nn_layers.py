import unittest
import numpy as np
import os, shutil
import tempfile
import coremltools.models.datatypes as datatypes
from coremltools.models import neural_network as neural_network
import coremltools
from nose.plugins.attrib import attr
import itertools

np.random.seed(10)

class CorrectnessTest(unittest.TestCase):
    
    def _compare_shapes(self, np_preds, coreml_preds):
        if np.squeeze(np_preds).shape != np.squeeze(coreml_preds).shape:
            return False
        else: 
            return True    
    
    def _compare_predictions(self, np_preds, coreml_preds, delta = .01):
        np_preds = np_preds.flatten()
        coreml_preds = coreml_preds.flatten()
        for i in range(len(np_preds)):
            max_den = max(1.0, np_preds[i], coreml_preds[i])
            if np.abs(np_preds[i] / max_den - coreml_preds[i] / max_den) > delta:
                return False
        return True
        

def get_size_after_stride(X, params):
    start = params["start"]
    end = params["end"]
    stride = params["stride"]  
    if params["axis"] == 'width': axis = 2
    if params["axis"] == 'height': axis = 1
    if params["axis"] == 'channel': axis = 0
    N = X.shape[axis]
    if end < 0: end = end + N 
    end = min(end, N)
    if start > N-1:
        L = 0
    else:
        L = np.floor((end - 1 - start)/stride) + 1
        if L<0 : L = 0
    return L         

def get_numpy_predictions_slice(X, params):
    start = params["start"]
    end = params["end"]
    stride = params["stride"]
    if params["axis"] == 'width': return X[:,:,start:end:stride]
    if params["axis"] == 'height': return X[:,start:end:stride,:]
    if params["axis"] == 'channel': return X[start:end:stride,:,:]
    
def get_coreml_predictions_slice(X, params):
    coreml_preds = []
    eval = True
    try:
        input_dim = X.shape
        output_dim = (1, 1, 1) #some random dimensions here: we are going to remove this information later
        input_features = [('data', datatypes.Array(*input_dim))]
        output_features = [('output', datatypes.Array(*output_dim))]
        builder = neural_network.NeuralNetworkBuilder(input_features, output_features)
        builder.add_slice('slice', 'data', 'output', start_index = params["start"], 
                            end_index = params["end"], stride = params["stride"], axis = params["axis"])                 
        #Remove output shape by deleting and adding an output
        del builder.spec.description.output[-1]                            
        output = builder.spec.description.output.add()
        output.name = 'output' 
        output.type.multiArrayType.dataType = coremltools.proto.FeatureTypes_pb2.ArrayFeatureType.ArrayDataType.Value('DOUBLE')
        #save the model                        
        model_dir = tempfile.mkdtemp()
        model_path = os.path.join(model_dir, 'test_layer.mlmodel')                        
        coremltools.utils.save_spec(builder.spec, model_path)
        #preprare input and get predictions
        coreml_model = coremltools.models.MLModel(model_path)
        coreml_input = {'data': X}
        coreml_preds = coreml_model.predict(coreml_input)['output']
        if os.path.exists(model_dir):
            shutil.rmtree(model_dir)
    except RuntimeError as e:
        print(e)
        eval = False        
        
    return coreml_preds, eval    
    
def get_numpy_predictions_reduce(X, params):
    if params["axis"] == 'CHW': axis = (0,1,2)
    if params["axis"] == 'HW' : axis = (1,2)
    if params["axis"] == 'C'  : axis = 0
    if params["axis"] == 'H'  : axis = 1
    if params["axis"] == 'W'  : axis = 2
    
    if params["mode"] == 'sum': return np.sum(X, axis)
    if params["mode"] == 'avg': return np.mean(X, axis)
    if params["mode"] == 'prod': return np.prod(X, axis)
    if params["mode"] == 'logsum': return np.sum(np.log(X+1e-6), axis)
    if params["mode"] == 'sumsquare': return np.sum(X ** 2, axis)
    if params["mode"] == 'L2': return np.sqrt(np.sum(X ** 2, axis))
    if params["mode"] == 'L1': return np.sum(np.abs(X), axis)
    if params["mode"] == 'max': return np.amax(X, axis)
    if params["mode"] == 'min': return np.amin(X, axis)
    if params["mode"] == 'argmax': return np.argmax(X, axis)

def get_coreml_predictions_reduce(X, params):
    coreml_preds = []
    eval = True
    try:
        input_dim = X.shape
        output_dim = (1, 1, 1) #some random dimensions here: we are going to remove this information later
        input_features = [('data', datatypes.Array(*input_dim))]
        output_features = [('output', datatypes.Array(*output_dim))]
        builder = neural_network.NeuralNetworkBuilder(input_features, output_features)
        builder.add_reduce('reduce', 'data', 'output', axis = params["axis"], mode = params["mode"])                 
        #Remove output shape by deleting and adding an output
        del builder.spec.description.output[-1]                            
        output = builder.spec.description.output.add()
        output.name = 'output' 
        output.type.multiArrayType.dataType = coremltools.proto.FeatureTypes_pb2.ArrayFeatureType.ArrayDataType.Value('DOUBLE')
        #save the model                        
        model_dir = tempfile.mkdtemp()
        model_path = os.path.join(model_dir, 'test_layer.mlmodel')                        
        coremltools.utils.save_spec(builder.spec, model_path)
        #preprare input and get predictions
        coreml_model = coremltools.models.MLModel(model_path)
        coreml_input = {'data': X}
        coreml_preds = coreml_model.predict(coreml_input)['output']
        if os.path.exists(model_dir):
            shutil.rmtree(model_dir)
    except RuntimeError as e:
        print(e)
        eval = False        
        
    return coreml_preds, eval
        

class SimpleTest(CorrectnessTest):
    
    def test_tiny_upsample_linear_mode(self):
                
        #create a tiny mlmodel
        input_dim = (1,1,3) #(C,H,W)
        input_features = [('data', datatypes.Array(*input_dim))]
        output_features = [('output', None)]
        
        builder = neural_network.NeuralNetworkBuilder(input_features, 
                output_features)
        builder.add_upsample(name= 'upsample', 
                             scaling_factor_h = 2, scaling_factor_w = 3, 
                             input_name= 'data', output_name= 'output', 
                             mode = 'BILINEAR')
        
        #save the model
        model_dir = tempfile.mkdtemp()
        model_path = os.path.join(model_dir, 'test_layer.mlmodel')                        
        coremltools.utils.save_spec(builder.spec, model_path)
        
        #preprare input and get predictions
        coreml_model = coremltools.models.MLModel(model_path)
        coreml_input = {'data': np.reshape(np.array([1.0,2.0,3.0]), (1,1,3))}
        coreml_preds = coreml_model.predict(coreml_input)['output']
        
        #harcoded for this simple test case
        numpy_preds = np.array([[1, 1.333, 1.666, 2, 2.333, 2.666, 3, 3, 3],\
                [1, 1.333, 1.6666, 2, 2.33333, 2.6666, 3, 3, 3]])
        #numpy_preds = np.array([[1, 1, 1, 2, 2, 2, 3, 3, 3],[1, 1, 1, 2, 2, 2, 3, 3, 3]])
        #Test
        self.assertTrue(self._compare_shapes(numpy_preds, coreml_preds))
        self.assertTrue(self._compare_predictions(numpy_preds, coreml_preds))
        
        if os.path.exists(model_dir):
            shutil.rmtree(model_dir)
    
    def test_LRN(self):
        
        #create a tiny mlmodel
        input_dim = (1,3,3)
        input_features = [('data', datatypes.Array(*input_dim))]
        output_features = [('output', datatypes.Array(*input_dim))]
                
        builder = neural_network.NeuralNetworkBuilder(input_features, 
                output_features)
                
        builder.add_lrn(name= 'lrn', input_name = 'data', output_name = 'output',
                        alpha = 2, beta = 3, local_size = 1, k = 8)
                        
        #save the model
        model_dir = tempfile.mkdtemp()
        model_path = os.path.join(model_dir, 'test_layer.mlmodel')                        
        coremltools.utils.save_spec(builder.spec, model_path)
        
        #preprare input and get predictions
        coreml_model = coremltools.models.MLModel(model_path)
        coreml_input = {'data': np.ones((1,3,3))}
        coreml_preds = coreml_model.predict(coreml_input)['output']
        
        #harcoded for this simple test case
        numpy_preds = 1e-3 * np.ones((1,3,3))
        self.assertTrue(self._compare_shapes(numpy_preds, coreml_preds))
        self.assertTrue(self._compare_predictions(numpy_preds, coreml_preds))
        
        if os.path.exists(model_dir):
            shutil.rmtree(model_dir)                            
            
            
class StressTest(CorrectnessTest):            
    
    def test_slice_layer(self):
        '''
        Define Params
        '''
        params_dict = dict(
                         input_shape = [[30,100,8], [80,50,5], [4,12,5], [56,8,14]],    
                         axis = ['channel', 'height', 'width'],
                         start = [0,1,2,5],
                         end = [5,100,56,-1,-2,-4],
                         stride = [1,2,3]
                         )              
        params = [x for x in apply(itertools.product, params_dict.values())] 
        all_candidates = [dict(zip(params_dict.keys(), x)) for x in params]     
        valid_params = []               
        for pr in all_candidates:
            X = np.random.rand(*pr["input_shape"])
            if get_size_after_stride(X, pr):
                valid_params.append(pr)        
        print "Total params to be tested: ", len(valid_params), "out of canditates: ", len(all_candidates)
        '''
        Test
        '''
        failed_tests_compile = []
        failed_tests_shape = []
        failed_tests_numerical = []
        for i in range(len(valid_params)):
            params = valid_params[i]
            #print "=========: ", params
            #if i % 10 == 0: print "======== Testing {}/{}".format(str(i), str(len(valid_params)))
            X = np.random.rand(*params["input_shape"])
            np_preds = get_numpy_predictions_slice(X, params)
            coreml_preds, eval = get_coreml_predictions_slice(X, params)
            if eval is False:
                failed_tests_compile.append(params)
            else:
                if not self._compare_shapes(np_preds, coreml_preds):    
                    failed_tests_shape.append(params)
                elif not self._compare_predictions(np_preds, coreml_preds):
                    failed_tests_numerical.append(params)
                    
        self.assertEqual(failed_tests_compile,[])
        self.assertEqual(failed_tests_shape, [])
        self.assertEqual(failed_tests_numerical,[])
        
    def test_reduce_layer(self):
        '''
        Define Params
        '''
        if 1:
            params_dict = dict(
                       input_shape = [[3,10,8], [8,5,5], [4,12,10], [7,1,14]],    
                       mode = ['sum', 'avg', 'prod', 'logsum', 'sumsquare', 'L1', 'L2', 'max', 'min', 'argmax'],
                       axis = ['CHW', 'HW', 'C', 'H', 'W'],
                       )
        if 0:
            params_dict = dict(
                       input_shape = [[3,10,8]],    
                       mode = ['logsum'],
                       axis = ['HW'],
                       )                             
        params = [x for x in apply(itertools.product, params_dict.values())] 
        all_candidates = [dict(zip(params_dict.keys(), x)) for x in params]     
        valid_params = []               
        for pr in all_candidates:
            if pr["mode"] == 'argmax':
                if pr["axis"] == 'CHW' or pr["axis"] == 'HW':
                    continue            
            valid_params.append(pr)        
        print "Total params to be tested: ", len(valid_params), "out of canditates: ", len(all_candidates)
        '''
        Test
        '''
        failed_tests_compile = []
        failed_tests_shape = []
        failed_tests_numerical = []
        for i in range(len(valid_params)):
            params = valid_params[i]
            #print "=========: ", params
            #if i % 10 == 0: print "======== Testing {}/{}".format(str(i), str(len(valid_params)))
            X = np.random.rand(*params["input_shape"])
            np_preds = get_numpy_predictions_reduce(X, params)
            coreml_preds, eval = get_coreml_predictions_reduce(X, params)
            if eval is False:
                failed_tests_compile.append(params)
            else:
                if not self._compare_shapes(np_preds, coreml_preds):    
                    failed_tests_shape.append(params)
                elif not self._compare_predictions(np_preds, coreml_preds):
                    failed_tests_numerical.append(params)
                    
        self.assertEqual(failed_tests_compile,[])
        self.assertEqual(failed_tests_shape, [])
        self.assertEqual(failed_tests_numerical,[])    
            
            
            
            