import logging
import tensorflow as tf
from tensorflow import Tensor
import numpy as np
import pickle
import time
import os
from tqdm import tqdm
import json
import logging
import matplotlib.pyplot as plt
from gluonts.time_feature import time_features_from_frequency_str
from gluonts.model.forecast import SampleForecast
from gluonts.transform import (Chain ,
                               AddObservedValuesIndicator,
                               AddTimeFeatures,
                               AddAgeFeature,
                               VstackFeatures,
                               SwapAxes,
                               CanonicalInstanceSplitter,
                               InstanceSplitter)
from gluonts.transform.sampler import TestSplitSampler
from gluonts.dataset.field_names import FieldName
from .scaler import MeanScaler , NOPScaler
from .data_loader import TrainDataLoader_OnlyPast ,InferenceDataLoader_WithFuture, mergeIterOut , stackIterOut
# 将当前序列所在的编号(相当于告诉你当前的序列信息)变成一个embedding向量

class SharedSSM(object):
    def __init__(self, config , sess):
        self.config = config
        self.sess = sess

        #导入原始的数据 , 确定了 SSM 的数量 ， env_dim 的维度，将ListData对象存放在list中
        self.load_original_data()

        #将导入的原始数据放入dataloader中, 使其能产生placeholders需要的内容
        self.transform_data()

        # 开始搭建有可能Input 对应的 placeholder
        self.placeholders = {
            "past_environment": tf.placeholder(dtype=tf.float32,shape=[config.batch_size, config.past_length, self.env_dim],name="past_environment"),
            "past_env_observed": tf.placeholder(dtype=tf.float32,shape=[config.batch_size, config.past_length, self.env_dim],name="past_env_observed"),
            "pred_environment" : tf.placeholder(dtype=tf.float32, shape=[config.batch_size ,config.pred_length,self.env_dim], name="pred_environment"),
            "pred_env_observed" : tf.placeholder(dtype=tf.float32, shape=[config.batch_size ,config.pred_length,self.env_dim], name="pred_env_observed"),
            "past_time_feature": tf.placeholder(dtype=tf.float32,shape=[config.batch_size, config.past_length, self.time_dim],name="past_time_feature"),
            "pred_time_feature": tf.placeholder(dtype=tf.float32,shape=[config.batch_size, config.pred_length, self.time_dim],name="pred_time_feature"),
            "past_target" : tf.placeholder(dtype=tf.float32, shape=[config.batch_size , config.past_length, self.ssm_num ,1], name="past_target"),
            "past_target_observed" : tf.placeholder(dtype=tf.float32, shape=[config.batch_size , config.past_length, self.ssm_num ,1], name="past_target_observed"),
            "pred_target" : tf.placeholder(dtype=tf.float32, shape=[config.batch_size ,config.pred_length, self.ssm_num ,1], name="pred_target"),
            "pred_target_observed" : tf.placeholder(dtype=tf.float32, shape=[config.batch_size ,config.pred_length, self.ssm_num ,1], name="pred_target_observed")
        }

        # 放入可能出现的SSM参数
        #  A(transition)是对角矩阵表示在转移的时候尽可能保持不变, B(control) 和 C(emission) 从高斯分布中随机进行采样
        A = np.array([np.eye(config.dim_z).astype(np.float32) for _ in range(config.K)])  # (K, dim_z , dim_z)
        B = np.array([config.init_kf_matrices * np.random.randn(config.dim_z, config.dim_u).astype(np.float32)
                      for _ in range(config.K)])
        C = np.array([config.init_kf_matrices * np.random.randn(config.dim_a, config.dim_z).astype(np.float32)
                      for _ in range(config.K)])

        # 使用 对角矩阵 作为 Noise

    def load_original_data(self):
        name_prefix = 'data_process/processed_data/{}_{}_{}_{}.pkl'
        # 导入 target 以及 environment 的数据
        ds_names = ','.join([self.config.target,self.config.environment])
        if self.config.slice == 'overlap':
            series = self.config.timestep - self.config.past_length - self.config.pred_length + 1
            print('每个数据集的序列数量为 ,', series)
        target_path = [name_prefix.format(
            name, '%s_DsSeries_%d' % (self.config.slice, series),
                           'train_%d' % self.config.past_length, 'pred_%d' % self.config.pred_length,
        ) for name in self.config.target.split(',')]
        env_path = [name_prefix.format(
            name, '%s_DsSeries_%d' % (self.config.slice, series),
                           'train_%d' % self.config.past_length, 'pred_%d' % self.config.pred_length,
        ) for name in self.config.environment.split(',')]


        for path in target_path+env_path:
            # 循环 path 的时候 需要 得到当前 path 对应的 ds_name
            for ds_name in ds_names.split(','):
                if ds_name in path:
                    break
            if not os.path.exists(path) :
                logging.info('there is no dataset [%s] , creating...'%ds_name)
                os.system('python data_process/preprocessing.py -d={} -t={} -p={} -s={} -n={} -f={}'
                          .format(ds_name
                              , self.config.past_length
                              , self.config.pred_length
                              , self.config.slice
                              , self.config.timestep
                              , self.config.freq))
            else:
                logging.info(' dataset [%s] was found , good~~~' % ds_name)
        self.target_data , self.env_data = [] , []
        # 由于 target 应该都是 dim = 1 只是确定有多少个 SSM 而已
        for target in target_path:
            with open(target, 'rb') as fp:
                target_ds = pickle.load(fp)
                assert target_ds.metadata['dim'] == 1 , 'target 序列的维度都应该为1'
                self.target_data.append(target_ds)

        self.ssm_num = len(self.target_data)
        self.env_dim = 0
        for env in env_path:
            with open(env, 'rb') as fp:
                env_ds = pickle.load(fp)
                self.env_dim += env_ds.metadata['dim']
                self.env_data.append(env_ds)
        print('导入原始数据成功~~~')

    def transform_data(self):
        # 首先需要把 target
        time_features = time_features_from_frequency_str(self.config.freq)
        self.time_dim = len(time_features)
        transformation = Chain([
            SwapAxes(
                input_fields=[FieldName.TARGET],
                axes=[0,1],
            ),
            AddObservedValuesIndicator(
                target_field = FieldName.TARGET,
                output_field = FieldName.OBSERVED_VALUES,
            ),
            # TODO: 这里的 AddTimeFeatures，面对的ts, 维度应该为(features,T)
            AddTimeFeatures(
                start_field=FieldName.START,
                target_field=FieldName.TARGET,
                output_field=FieldName.FEAT_TIME,
                time_features=time_features,
                pred_length=self.config.pred_length,
            ),
            AddAgeFeature(
                target_field=FieldName.TARGET,
                output_field=FieldName.FEAT_AGE,
                pred_length=self.config.pred_length,
                log_scale=True,
            ),
            VstackFeatures(
                output_field=FieldName.FEAT_TIME,
                input_fields=[FieldName.FEAT_TIME, FieldName.FEAT_AGE]
            ),
            InstanceSplitter(
                target_field=FieldName.TARGET,
                is_pad_field=FieldName.IS_PAD,
                start_field=FieldName.START,
                forecast_start_field=FieldName.FORECAST_START,
                train_sampler=TestSplitSampler(),
                past_length=self.config.past_length,
                future_length=self.config.pred_length,
                output_NTC=True,
                time_series_fields=[
                    FieldName.FEAT_TIME,
                    FieldName.OBSERVED_VALUES
                ],
                pick_incomplete=False,
            )

        ])
        print('已设置时间特征~~')
        # 设置环境变量的 dataloader
        env_train_iters = [iter(TrainDataLoader_OnlyPast(
            dataset = self.env_data[i].train,
            transform = transformation,
            batch_size = self.config.batch_size,
            num_batches_per_epoch = self.config.num_batches_per_epoch,
        )) for i in range(len(self.env_data))]
        env_test_iters = [iter(InferenceDataLoader_WithFuture(
            dataset=self.env_data[i].test,
            transform=transformation,
            batch_size=self.config.batch_size,
        )) for i in range(len(self.env_data))]
        target_train_iters = [iter(TrainDataLoader_OnlyPast(
            dataset=self.target_data[i].train,
            transform=transformation,
            batch_size=self.config.batch_size,
            num_batches_per_epoch=self.config.num_batches_per_epoch,
        )) for i in range(len(self.target_data))]
        target_test_iters = [iter(InferenceDataLoader_WithFuture(
            dataset=self.target_data[i].test,
            transform=transformation,
            batch_size=self.config.batch_size,
        )) for i in range(len(self.target_data))]

        self.env_train_loader = mergeIterOut(env_train_iters,
                                             fields=[FieldName.OBSERVED_VALUES , FieldName.FEAT_TIME , FieldName.TARGET],
                                             include_future=True)
        self.target_train_loader = stackIterOut(target_train_iters,
                                                fields=[FieldName.OBSERVED_VALUES , FieldName.FEAT_TIME , FieldName.TARGET],
                                                dim=2,
                                                include_future=False)
        self.env_test_loader = mergeIterOut(env_test_iters,
                                            fields=[FieldName.OBSERVED_VALUES , FieldName.FEAT_TIME , FieldName.TARGET],
                                            include_future=True)
        self.target_test_loader = stackIterOut(target_test_iters,
                                               fields=[FieldName.OBSERVED_VALUES, FieldName.FEAT_TIME,
                                                        FieldName.TARGET],
                                               dim=2,
                                               include_future=True)
        # 做training 时
        print('\n----- training数据集 ------')
        for batch_no , batch_data in enumerate(self.target_train_loader , start=1):
            if batch_data != None :
                print('第{}个batch的内容 past_target: {}  , past_time : {} , past_observed :{} ,'.format(
                    batch_no,
                    batch_data['past_target'].shape ,
                    batch_data['past_time_feat'].shape,
                    batch_data['past_%s' % (FieldName.OBSERVED_VALUES)].shape
                ))
            else:
                print('第' , batch_no , '内容为空')
        # 做inference 时
        print('\n----- inference数据集 ------')
        for batch_no ,batch_data in enumerate(self.target_test_loader , start=1):
            if batch_data != None:
                print('第{}个batch的内容 past_target: {} , future_target: {} '
                      ', past_time : {} , future_time : {}'
                      ', past_observed : {} , future_observed : {}'.format(
                    batch_no,
                    batch_data['past_target'].shape, batch_data['future_target'].shape,
                    batch_data['past_time_feat'].shape, batch_data['future_time_feat'].shape,
                    batch_data['past_%s' % (FieldName.OBSERVED_VALUES)].shape,
                    batch_data['future_%s' % (FieldName.OBSERVED_VALUES)].shape
                ))
            else:
                print('第' , batch_no ,'内容为空')
        exit()

    def build_module(self):
        with tf.variable_scope('time_feature_exactor', initializer=tf.contrib.layers.xavier_initializer() , reuse=tf.AUTO_REUSE):
            self.time_feature_exactor = []
            for k in range(self.config.time_exact_layers):
                cell = tf.nn.rnn_cell.LSTMCell(num_units=self.config.time_exact_cells)
                cell = tf.nn.rnn_cell.ResidualWrapper(cell) if k > 0 else cell
                cell = (
                    tf.nn.rnn_cell.DropoutWrapper(cell,state_keep_prob=1.0-self.dropout_rate)
                    if self.dropout_rate > 0.0
                    else cell
                )
                self.time_feature_exactor.append(cell)

            self.time_feature_exactor = tf.nn.rnn_cell.MultiRNNCell(self.time_feature_exactor)


            if self.scaling:
                self.scaler = MeanScaler(keepdims=False)
            else:
                self.scaler = NOPScaler(keepdims=False)

            return self
        pass
    def build_train_forward(self):
        pass

    def build_predict_forward(self):
        pass

    def initialize_variables(self):
        """ Initialize variables or load saved model
        :return: self
        """
        # Setup saver
        self.saver = tf.train.Saver()

        # Initialize or reload variables
        if self.config.reload_model is not '':
            print("Restoring model in %s" % self.config.reload_model)
            params_path = os.path.join(self.config.reload_model , "model_params")
            param_name = os.listdir(params_path)[0].split('.')[0]
            params_path = os.path.join(params_path, param_name)
            self.saver.restore(self.sess, params_path)
        else:
            print("Training to get new model params")
            self.sess.run(tf.global_variables_initializer())
        return self

    def train(self):
        #如果导入已经有的信息,不进行训练
        if self.config.reload_model != '':
            return
        sess = self.sess
        self.writer_path = os.path.join(self.config.logs_dir,
                                   '_'.join([self.config.dataset, str(self.config.past_length)
                                                , str(self.config.pred_length)]))
        if not os.path.isdir(self.writer_path):
            os.mkdir(self.writer_path)
        #将当前训练的参数输入到路径中
        hyperparameter_json_path = os.path.join(self.writer_path, "hyperparameter.json")
        config_dict = {k:self.config[k].value for k in self.config}
        with open(hyperparameter_json_path, 'w') as f:
            json.dump(config_dict, f, indent=4)

        num_batches = self.config.num_batches_per_epoch
        best_epoch_info = {
            'epoch_no': -1,
            'metric_value': np.Inf
        }
        # vars = tf.trainable_variables()
        # for v in vars:
        #     print(v)
        # exit()

        for epoch_no in range(self.config.epochs):
            #执行一系列操作
            #产生新的数据集
            tic = time.time()
            epoch_loss = 0.0

            with tqdm(range(num_batches)) as it:
                for batch_no in it :
                    batch_input , _  = next(self.train_iter)
                    placeholders = [self.feat_static_cat , self.past_observed_values
                        , self.past_seasonal_indicators, self.past_time_feat, self.past_target ]
                    feed_dict = dict(zip(placeholders,batch_input))

                    batch_output , _   = sess.run([self.train_result , self.train_op]
                                            , feed_dict=feed_dict)
                    epoch_loss += np.sum(batch_output)
                    avg_epoch_loss = epoch_loss/((batch_no+1)*self.config.batch_size)

                    it.set_postfix(
                        ordered_dict={
                            "avg_epoch_loss":  avg_epoch_loss
                        },
                        refresh=False,
                    )
            toc = time.time()
            logging.info(
                "Epoch[%d] Elapsed time %.3f seconds",
                epoch_no,
                (toc - tic),
            )

            logging.info(
                "Epoch[%d] Evaluation metric '%s'=%f",
                epoch_no,
                "epoch_loss",
                avg_epoch_loss,
            )
            logging.info(
                "Epoch[%d] the best of this training(before this epoch) '%d <==> %f'",
                epoch_no,
                best_epoch_info['epoch_no'],
                best_epoch_info['metric_value'],
            )

            if avg_epoch_loss < best_epoch_info['metric_value']:
                best_epoch_info['metric_value'] = avg_epoch_loss
                best_epoch_info['epoch_no'] = epoch_no
                self.save_path = os.path.join(self.writer_path , "model_params"
                                 ,'best_{}_{}_{}'.format(self.dataset, self.past_length,self.prediction_length)
                            )
                self.saver.save(sess, self.save_path)
                #'/{}_{}_best.ckpt'.format(self.dataset,epoch_no)

        logging.info(
            f"Loading parameters from best epoch "
            f"({best_epoch_info['epoch_no']})"
        )

        logging.info(
            f"Final loss: {best_epoch_info['metric_value']} "
            f"(occurred at epoch {best_epoch_info['epoch_no']})"
        )

        # save net parameters
        logging.getLogger().info("End model training")

    def predict(self):
        sess = self.sess
        self.all_forecast_result = []
        # 如果是 训练之后接着的 predict 直接采用之前 train 产生的save_path
        if hasattr(self ,'save_path'):
            path = self.save_path
            try:
                self.saver.restore(sess, save_path=path)
                print('there is no problem in restoring model params')
            except:
                print('something bad appears')
            finally:
                print('whatever ! life is still fantastic !')
        iteration = len(self.env_data) // self.batch_size + 1 \
                    if len(self.env_data) % self.batch_size != 0 \
                    else len(self.env_data) // self.batch_size
        for batch_no in range(iteration):
            test_input , other_info = next(self.test_iter)
            placeholders = [self.feat_static_cat, self.past_observed_values
                , self.past_seasonal_indicators, self.past_time_feat, self.past_target
                , self.future_seasonal_indicators , self.future_time_feat]
            feed_dict = dict(zip(placeholders, test_input))

            test_output = sess.run(self.predict_result,feed_dict =  feed_dict)

            outputs = [
                np.concatenate(s)[:self.num_sample_paths]
                for s in zip(test_output)
            ]
            print('当前正在处理第 %d 个 batch_no 的结果' % (batch_no))
            for i , output in enumerate(outputs):
                # 最后一个不满 batch_size 的放弃它

                sample_forecast = SampleForecast(
                    samples = output,
                    start_date = other_info[0][i],
                    freq = self.config.freq,
                )
                # if batch_no < len(self.test_data) // self.batch_size :
                #     self.all_forecast_result.append(sample_forecast)
                if batch_no*self.batch_size + i < len(self.env_data):
                    self.all_forecast_result.append(sample_forecast)
                else:
                    print('%d batch %d sample was complicate , throw away' %(batch_no,i))
                    break


        return self


    def evaluate(self, forecast=None):
        pass


def plot_prob_forecasts(ts_entry, forecast_entry,ds_name ,no ,plot_length):
    prediction_intervals = (50.0, 90.0)
    legend = ["observations", "median prediction"] + [f"{k}% prediction interval" for k in prediction_intervals][::-1]

    fig, ax = plt.subplots(1, 1, figsize=(10, 7))
    ts_entry[-plot_length:].plot(ax=ax)  # plot the time series
    forecast_entry.plot(prediction_intervals=prediction_intervals, color='g')
    plt.grid(which="both")
    plt.legend(legend, loc="upper left")
    plt.savefig('pic/{}_result/result_output_tf_{}.png'.format(ds_name,no))
    plt.close(fig)

def evaluate_up_down(ground_truth , mc_forecast):
    # 0代表跌 1代表涨
    ground_truth_labels = [1 if truth.iloc[-1].values[0] > truth.iloc[-2].values[0] else 0 for truth in ground_truth]
    forecast_labels = [1 if mc_forecast[i].mean[0] > ground_truth[i].iloc[-2].values[0] else 0
                       for i in range(len(mc_forecast))]
    acc = accuracy_score(ground_truth_labels , forecast_labels)
    return {'acc' : acc}