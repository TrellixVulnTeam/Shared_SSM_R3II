# -*- utf-8 -*-
# author : joelonglin

from gluonts.lzl_finance.model.deepstate_Compared.model.deepstate import DeepStateNetwork
import pickle
from gluonts.lzl_finance.model.deepstate_Compared.utils.config import reload_config
import tensorflow as tf
tf.compat.v1.logging.set_verbosity(tf.compat.v1.logging.ERROR)
import os
os.environ["CUDA_VISIBLE_DEVICES"] = "1"

cl = tf.app.flags
# reload_model =  'logs/btc_eth/Dec_25_17:27:07_2019'
reload_model = ''
cl.DEFINE_string('reload_model' ,reload_model,'model to reload')
cl.DEFINE_string('logs_dir','logs/btc_eth(deep_state)','file to print log')

#train configuration
cl.DEFINE_integer('epochs' , 50 , 'Number of epochs that the network will train (default: 1).')
cl.DEFINE_bool('shuffle' , False ,'whether to shuffle the train dataset')
cl.DEFINE_integer('batch_size' ,  32 , 'Numbere of examples in each batch')
cl.DEFINE_integer('num_batches_per_epoch' , 60 , 'Numbers of batches at each epoch')
cl.DEFINE_float('learning_rate' , 0.001 , 'Initial learning rate')

# network configuration
cl.DEFINE_integer('num_layers' ,2,'num of lstm cell layers')
cl.DEFINE_integer('num_cells' ,40 , 'hidden units size of lstm cell')
cl.DEFINE_string('cell_type' , 'lstm' , 'Type of recurrent cells to use (available: "lstm" or "gru"')
cl.DEFINE_float('dropout_rate' , 0.1 , 'Dropout regularization parameter (default: 0.1)')
cl.DEFINE_string('embedding_dimension' , '' , ' Dimension of the embeddings for categorical features')

# dataset configuration
cl.DEFINE_string('target' , 'btc,eth' , 'Name of the target dataset')
cl.DEFINE_string('environment' , 'gold' , 'Name of the dataset ')
cl.DEFINE_integer('timestep' , 503 , 'length of the series') #这个序列的长度实际上也决定了样本数量的大小
cl.DEFINE_string('slice' , 'overlap' , 'how to slice the dataset')
cl.DEFINE_string('freq','1D','Frequency of the data to train on and predict')
cl.DEFINE_integer('past_length' ,90,'This is the length of the training time series')
cl.DEFINE_integer('pred_length' , 5 , 'Length of the prediction horizon')
cl.DEFINE_bool('add_trend' , False , 'Flag to indicate whether to include trend component in the SSM')

# prediciton configuration
cl.DEFINE_integer('num_eval_samples', '100', 'Number of samples paths to draw when computing predictions')
cl.DEFINE_bool('scaling', True, 'whether to scale the target and observed')
cl.DEFINE_bool('use_feat_dynamic_real', False, 'Whether to use the ``feat_dynamic_real`` field from the data')
cl.DEFINE_bool('use_feat_static_cat', False, 'Whether to use the ``feat_static_cat`` field from the data')
cl.DEFINE_string('cardinality' , '2' , 'Number of values of each categorical feature.')




def main(_):
    if ('/lzl_finance' not in os.getcwd()):
         os.chdir('gluonts/lzl_finance')
         print('change os dir : ',os.getcwd())
    if('deepstate_Compared' in os.getcwd()):
        os.chdir('../..')
        print('change os dir : ' , os.getcwd())
    config = cl.FLAGS
    print('reload model : ' , config.reload_model)
    config = reload_config(config)
    # for i in config:
    #     try:
    #         print(i , ':' , eval('config.{}'.format(i)))
    #     except:
    #         print('当前 ' , i ,' 属性获取有问题')
    #         continue
    # exit()
    configuration = tf.compat.v1.ConfigProto()
    configuration.gpu_options.allow_growth = True
    with tf.compat.v1.Session(config=configuration) as sess:
        dssm = DeepStateNetwork(config=config,sess=sess)\
            .build_module().build_train_forward().build_predict_forward().initialize_variables()
        dssm.train()
        # dssm.predict()
        # dssm.evaluate()



if __name__ == '__main__':
   tf.app.run()