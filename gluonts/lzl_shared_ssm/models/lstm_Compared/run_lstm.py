# -*- utf-8 -*-
# author : joelonglin

from gluonts.lzl_shared_ssm.models.lstm_Compared.model import Common_LSTM
from gluonts.lzl_shared_ssm.models.lstm_Compared.utils import reload_config
import tensorflow as tf
tf.compat.v1.logging.set_verbosity(tf.compat.v1.logging.ERROR)
import os
os.environ["CUDA_VISIBLE_DEVICES"] = "1"

cl = tf.app.flags
# reload_model =  'logs/btc_eth/Dec_25_17:27:07_2019'
reload_model = ''
cl.DEFINE_string('reload_model' ,reload_model,'models to reload')
cl.DEFINE_string('logs_dir','logs/btc_eth(common_lstm)','file to print log')

#train configuration
cl.DEFINE_integer('epochs' , 30 , 'Number of epochs that the network will train (default: 1).')
cl.DEFINE_bool('shuffle' , False ,'whether to shuffle the train dataset')
cl.DEFINE_integer('batch_size' ,  32 , 'Numbere of examples in each batch')
cl.DEFINE_integer('num_batches_per_epoch' , 13 , 'Numbers of batches at each epoch')
cl.DEFINE_float('learning_rate' , 0.001 , 'Initial learning rate')

# network configuration
cl.DEFINE_bool('scaling' , True , 'whether use scaler to scale the data')
cl.DEFINE_bool('use_time_feat' , True , 'whether put the time feature into lstm')
cl.DEFINE_bool('use_orig_compute_loss' , True , 'compute the loss function with original data or scaled data')
cl.DEFINE_integer('num_layers' ,2,'num of lstm cell layers')
cl.DEFINE_integer('num_cells' ,40 , 'hidden units size of lstm cell')
cl.DEFINE_string('cell_type' , 'lstm' , 'Type of recurrent cells to use (available: "lstm" or "gru"')
cl.DEFINE_float('dropout_rate' , 0.1 , 'Dropout regularization parameter (default: 0.1)')

# dataset configuration
cl.DEFINE_string('target' , 'btc,eth' , 'Name of the target dataset')
cl.DEFINE_string('environment' , 'gold' , 'Name of the dataset ')
cl.DEFINE_integer('timestep' , 503 , 'length of the series') #这个序列的长度实际上也决定了样本数量的大小
cl.DEFINE_string('slice' , 'overlap' , 'how to slice the dataset')
cl.DEFINE_string('freq','1D','Frequency of the data to train on and predict')
cl.DEFINE_integer('past_length' ,90,'This is the length of the training time series')
cl.DEFINE_integer('pred_length' , 5 , 'Length of the prediction horizon')



def main(_):
    if ('/lzl_shared_ssm' not in os.getcwd()):
         os.chdir('gluonts/lzl_shared_ssm')
         print('change os dir : ',os.getcwd())
    if('lstm_Compared' in os.getcwd()):
        os.chdir('../..')
        print('change os dir : ' , os.getcwd())
    config = cl.FLAGS
    print('reload models : ' , config.reload_model)
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
        dssm = Common_LSTM(config=config, sess=sess)\
            .build_module().build_train_forward().build_predict_forward().initialize_variables()
        dssm.train()
        # dssm.predict()
        # dssm.evaluate()



if __name__ == '__main__':
   tf.app.run()