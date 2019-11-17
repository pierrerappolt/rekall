"""This module performs coordinate descent over the search space."""

from rekall.tuner import Tuner
from rekall.tuner.random_tuner import RandomTuner

class CoordinateDescentTuner(Tuner):
    
    def line_search(self, config, cur_param, epsilon, budget, cur_score = 0):
        '''
        Vary cur_param within the bounds of the search_space (holding the other
        parameters constant), maximizing the accuracy function.

        Let X be the current param, and let F(X) represent the accuracy function.
        Let Y be the range of X in the search_space.

        If F(X + epsilon * Y) > F(X):
          * Find the smallest positive integer l such that
            F(X + l * epsilon * Y) < F(X + (l - 1) * epsilon * Y), and return
            X + (l - 1) * epsilon * Y as the new value of the parameter
        Otherwise:
          * Find the smallest positive integer l such that
            F(X - l * epsilon * Y) < F(X - (l - 1) * epsilon * Y), and return
            X - (l - 1) * epsilon * Y as the new value of the parameter
        '''
        minval, maxval = self.search_space[cur_param]['range']
        Y = maxval - minval
        delta = epsilon * Y

        orig_val = config[cur_param]
        if orig_val + delta > maxval and orig_val - delta < minval:
            return orig_val, cur_score

        # Determine direction
        cur_val = orig_val + delta
        config[cur_param] = cur_val
        
        local_cost = 0
        score = self.evaluate_config(config)
        local_cost += 1

        # If the score is worse, try other direction
        if ((self.maximize and score < cur_score) or
            (not self.maximize and score > cur_score)):
            delta = -1 * delta
            cur_val = orig_val + delta
            config[cur_param] = cur_val
            
            score = self.evaluate_config(config)
            local_cost += 1

            # Neither direction works
            if ((self.maximize and score < cur_score) or
                (not self.maximize and score > cur_score)):
                return orig_val, cur_score

        # Find the optimal value of l
        prev_score = score
        while local_cost < budget:
            if cur_val + delta > maxval or cur_val + delta < minval:
                break
            cur_val += delta
            config[cur_param] = cur_val
            
            score = self.evaluate_config(config)
            local_cost += 1
            
            # If this score is worse
            if ((self.maximize and score < cur_score) or
                (not self.maximize and score > cur_score)):
                # Go back one step
                cur_val -= delta
                break
            prev_score = score

        return cur_val, prev_score
    
    def tune_impl(self, **kwargs):
        '''
        Start with the midpoint of the search space
        Then cycle through co-ordinates.
        For each co-ordinate:
          * If the co-ordinate is discrete, try all the choices
          * If the co-ordinate is numerical, run line search with alpha and
            a budget of 10
        If all the co-ordinates stay the same, try again with alpha = alpha * decay_rate.
        
        args in kwargs:
            'alpha': initial alpha value for line search
            'decay_rate': rate to decay alpha
            'init_method': How to iitialize the first config.
                Either 'average' or 'random'. If not specified, default to 'average'.
                'average' initializes the config at the average of continuous ranges,
                'random' randomly initializes the config.
        '''
        if 'alpha' not in kwargs or 'decay_rate' not in kwargs:
            print('Coordinate descent requires alpha and decay_rate!')
            return
            
        alpha = kwargs['alpha']
        decay_rate = kwargs['decay_rate']
        
        if 'init_method' in kwargs:
            init_method = kwargs['init_method']
        else:
            init_method = 'average'

        coordinates = sorted(list(self.search_space.keys()))

        if init_method is 'average':
            config = {}

            # Initialize the config
            for coordinate in coordinates:
                param = self.search_space[coordinate]
                if isinstance(param, dict):
                    if 'range' in param:
                        minval, maxval = param['range']
                        config[coordinate] = (maxval + minval) / 2
        #             elif 'subset' in param:
        #                 choices = param['subset']
        #                 config[k] = choices[:random.randint(1, len(param['subset']))]
                elif isinstance(param, list):
                    config[k] = param[0]
        elif init_method is 'random':
            config = RandomTuner.generate_configs(self.search_space, 1)[0]
        else:
            print('{} is invalid init_method!'.format(init_method))
            return

        score = self.evaluate_config(config)

        cur_score = score
        rounds = 0
        while self.cost < self.budget:
            self.log_msg('Round {}, current cost {}'.format(rounds, self.cost))
            changed = False
            for coordinate in coordinates:
                if self.cost > self.budget:
                    break
                self.log_msg('Coordinate {}, current cost {}'.format(coordinate, self.cost))
                orig_val = config[coordinate]
                param = self.search_space[coordinate]

                # Discrete params
                if isinstance(param, list):
                    max_score = cur_score
                    best_choice = orig_val
                    for choice in param:
                        if choice == orig_val:
                            continue
                        config[coordinate] = choice

                        score = self.evaluate_config(config)
                        
                        if ((self.maximize and score > max_score) or
                            (not self.maximize and score < max_score)):
                            best_choice = choice
                            max_score = score
                    self.log_msg('Old: {}, new: {}'.format(orig_val, best_choice))
                    if best_choice != orig_val:
                        changed = True
                    config[coordinate] = best_choice
                    cur_score = max_score
                # Numerical params
                elif isinstance(param, dict):
                    if 'range' in param:
                        best_choice, max_score = self.line_search(
                            config, coordinate, alpha, 10,
                            cur_score = cur_score)

                        self.log_msg('Old: {}, New: {}'.format(orig_val, best_choice))
                        if best_choice != orig_val:
                            changed = True
                        config[coordinate] = best_choice
                        cur_score = max_score

            if not changed:
                alpha *= decay_rate
                self.log_msg('New alpha: {}, current cost {}'.format(alpha, self.cost))
                if alpha < .000001:
                    break
            rounds += 1