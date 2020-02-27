# -*- utf-8 -*-
# author : joelonglin

from gluonts.lzl_finance.model.shared_SSM import SharedSSM
import pickle
from gluonts.lzl_deepstate.utils.config import  reload_config
import tensorflow as tf
tf.compat.v1.logging.set_verbosity(tf.compat.v1.logging.ERROR)
import os
os.environ["CUDA_VISIBLE_DEVICES"] = "1"

cl = tf.app.flags
# reload_model =  'logs/btc_eth/Dec_25_17:27:07_2019'
reload_model = ''
cl.DEFINE_string('reload_model' ,reload_model,'model to reload')
cl.DEFINE_string('logs_dir','logs/btc_eth','file to print log')

# SSM configuration
cl.DEFINE_integer('dim_a', 1, 'Dimension of the observation in the LGSSM')
cl.DEFINE_integer('dim_z', 4, 'Dimension of the latent state in the LGSSM')
# TODO: 这里面的 dim_u 由 LSTM中提取公共信息特征维度，最好能够有一个可解释性的维度
cl.DEFINE_integer('dim_u', 10 , 'Dimension of the inputs , which come from LSTM')
cl.DEFINE_integer('K', 2, 'Number of filters in mixture')
# TODO：这里关于Noise的强度，也可以参考DeepState中，根据timestamp生成的特征获取噪声的大小
cl.DEFINE_float('noise_emission', 0.03, 'Noise level for the measurement noise matrix')
cl.DEFINE_float('noise_transition', 0.08, 'Noise level for the process noise matrix')
cl.DEFINE_float('init_kf_matrices', 0.05, 'initialize the B and C matrix')
cl.DEFINE_float('init_cov', 20.0, 'Variance of the initial state')

# shared time_feature network configuration
cl.DEFINE_integer('time_exact_layers' ,2,'num of lstm cell layers')
cl.DEFINE_integer('time_exact_cells' ,40 , 'hidden units size of lstm cell')
cl.DEFINE_string('cell_type' , 'lstm' , 'Type of recurrent cells to use (available: "lstm" or "gru"')
cl.DEFINE_float('dropout_rate' , 0.1 , 'Dropout regularization parameter (default: 0.1)')

# dynamic parameter network configuration
cl.DEFINE_boolean('alpha_rnn', True, 'Use LSTM RNN for alpha')
cl.DEFINE_integer('alpha_units', 50, 'Number of units in alpha network')
cl.DEFINE_integer('alpha_layers', 2, 'Number of layers in alpha network (if alpha_rnn=False)')
cl.DEFINE_string('alpha_activation', 'relu', 'Activation function in alpha (if alpha_rnn=False)')
cl.DEFINE_integer('fifo_size', 1, 'Number of items in the alpha FIFO memory (if alpha_rnn=False)')

# dataset configuration
cl.DEFINE_string('target' , 'btc,eth' , 'Name of the target dataset')
cl.DEFINE_string('environment' , 'gold' , 'Name of the dataset ')
cl.DEFINE_integer('timestep' , 503 , 'length of the series') #这个序列的长度实际上也决定了样本数量的大小
cl.DEFINE_string('slice' , 'overlap' , 'how to slice the dataset')
cl.DEFINE_string('freq','1D','Frequency of the data to train on and predict')
cl.DEFINE_integer('past_length' ,90,'This is the length of the training time series')
cl.DEFINE_integer('pred_length' , 5 , 'Length of the prediction horizon')

# prediciton configuration
cl.DEFINE_integer('num_eval_samples', '100', 'Number of samples paths to draw when computing predictions')
cl.DEFINE_bool('scaling', True, 'whether to scale the target and observed')
cl.DEFINE_bool('use_feat_dynamic_real', False, 'Whether to use the ``feat_dynamic_real`` field from the data')
cl.DEFINE_bool('use_feat_static_cat', True, 'Whether to use the ``feat_static_cat`` field from the data')
cl.DEFINE_string('cardinality' , '2' , 'Number of values of each categorical feature.')

#train configuration
cl.DEFINE_integer('epochs' , 25 , 'Number of epochs that the network will train (default: 1).')
cl.DEFINE_bool('shuffle' , False ,'whether to shuffle the train dataset')
cl.DEFINE_integer('batch_size' ,  32 , 'Numbere of examples in each batch')
cl.DEFINE_integer('num_batches_per_epoch' , 200 , 'Numbers of batches at each epoch')
cl.DEFINE_float('learning_rate' , 0.001 , 'Initial learning rate')


def main(_):
    if ('/lzl_finance' not in os.getcwd()):
         os.chdir('gluonts/lzl_finance')
         print('change os dir : ',os.getcwd())
    config = cl.FLAGS
    print('reload model : ' , config.reload_model)
    config = reload_config(config)
    configuration = tf.compat.v1.ConfigProto()
    configuration.gpu_options.allow_growth = True
    with tf.compat.v1.Session(config=configuration) as sess:
        sharedSSM = SharedSSM(config=config, sess=sess)\
            .build_module().build_train_forward().build_predict_forward().initialize_variables()
        sharedSSM.train()
        sharedSSM.predict()
        sharedSSM.evaluate()



if __name__ == '__main__':
   tf.app.run()


# for i in config:
#     try:
#         print(i , ':' , eval('config.{}'.format(i)))
#     except:
#         print('当前 ' , i ,' 属性获取有问题')
#         continue
# exit()