#!/usr/bin/python
# -*- coding: utf-8 -*-

"""
   This file belong to https://github.com/snolfi/evorobotpy
   and has been written by Stefano Nolfi and Paolo Pagliuca, stefano.nolfi@istc.cnr.it, paolo.pagliuca@istc.cnr.it
   salimans.py include an implementation of the OpenAI-ES algorithm described in
   Salimans T., Ho J., Chen X., Sidor S & Sutskever I. (2017). Evolution strategies as a scalable alternative to reinforcement learning. arXiv:1703.03864v2
   requires es.py, policy.py, and evoalgo.py 
"""

import numpy as np
from numpy import zeros, ones, dot, sqrt
import math
import time
from evoalgo import EvoAlgo
from utils import ascendent_sort
import sys
import os
import configparser
import cma # CMA-ES implementation
import random


# Parallel implementation of Open-AI-ES algorithm developed by Salimans et al. (2017)
# the workers evaluate a fraction of the population in parallel
# the master post-evaluate the best sample of the last generation and eventually update the input normalization vector


class Algo(EvoAlgo):
    def __init__(self, env, policy, seed, fileini, filedir):
        EvoAlgo.__init__(self, env, policy, seed, fileini, filedir)

    def loadhyperparameters(self):

        if os.path.isfile(self.fileini):

            config = configparser.ConfigParser()
            config.read(self.fileini)
            self.maxsteps = 1000000
            self.noiseStdDev = 0.02
            self.symseed = 1
            self.saveeach = 60
            options = config.options("ALGO")
            for o in options:
                found = 0
                if o == "maxmsteps":
                    self.maxsteps = config.getint("ALGO", "maxmsteps") * 1000000
                    found = 1
                if o == "noisestddev":
                    self.noiseStdDev = config.getfloat("ALGO", "noiseStdDev")
                    found = 1
                if o == "symseed":
                    self.symseed = config.getint("ALGO", "symseed")
                    found = 1
                if o == "saveeach":
                    self.saveeach = config.getint("ALGO", "saveeach")
                    found = 1

                if found == 0:
                    print(
                        "\033[1mOption %s in section [ALGO] of %s file is unknown\033[0m"
                        % (o, filename)
                    )
                    print("available hyperparameters are: ")
                    print(
                        "maxmsteps [integer]       : max number of (million) steps (default 1)"
                    )
                    print("noiseStdDev [float]       : samples noise (default 0.02)")
                    print(
                        "symseed [0/1]             : same environmental seed to evaluate symmetrical samples [default 1]"
                    )
                    print(
                        "saveeach [integer]        : save file every N minutes (default 60)"
                    )

                    sys.exit()
        else:
            print(
                "\033[1mERROR: configuration file %s does not exist\033[0m"
                % (self.fileini)
            )

    def setProcess(self):
        self.loadhyperparameters()  # load hyperparameters
        self.center = np.copy(self.policy.get_trainable_flat())  # the initial centroid
        self.nparams = len(self.center)  # number of adaptive parameters
        self.cgen = 0  # currrent generation
        self.bestgfit = -99999999  # the best generalization fitness
        self.bfit = 0  # the fitness of the best sample
        self.gfit = (
            0  # the postevaluation fitness of the best sample of last generation
        )
        self.cma_es = cma.CMAEvolutionStrategy(self.center, self.noiseStdDev) # CMA-ES initialization
        self.number_niches = 10
        self.fitness = [-9999 for _ in range(self.number_niches)]
        self.candidates = [0 for _ in range(self.number_niches)]
        self.inormepisodes = (
            self.policy.ntrials / 100.0
        )  # number of normalization episode for generation (1% of generation episodes)
        self.tnormepisodes = (
            0.0  # total epsidoes in which normalization data should be collected so far
        )
        self.normepisodes = 0  # numer of episodes in which normalization data has been actually collected so far
        self.normalizationdatacollected = (
            False  # whether we collected data for updating the normalization vector
        )

    def savedata(self):
        self.save()  # save the best agent so far, the best postevaluated agent so far, and progress data across generations
        fname = self.filedir + "/S" + str(self.seed) + ".fit"
        fp = open(fname, "w")  # save summary
        fp.write(
            "Seed %d (%.1f%%) gen %d msteps %d bestfit %.2f bestgfit %.2f bestsam %.2f avgfit %.2f \n"
            % (
                self.seed,
                self.steps / float(self.maxsteps) * 100,
                self.cgen,
                self.steps / 1000000,
                self.bestfit,
                self.bestgfit,
                self.bfit,
                self.avgfit,
            )
        )
        fp.close()

    def evaluate(self, candidate, oniche=None):
        oniche_flag = True
        self.niche = self.niche % self.number_niches
        if oniche is None:
            oniche = self.niche
            oniche_flag = False
        self.policy.set_trainable_flat(candidate)
        self.policy.nn.normphase(
            0
        )  # normalization data is collected during the post-evaluation of the best sample of he previous generation
        eval_rews, eval_length = self.policy.rollout(
            self.policy.ntrials,
            seed= self.niches[oniche]
        )
        self.steps += eval_length
        if eval_rews > self.bestestfit[0]:
            self.bestestfit = (eval_rews, candidate)
            # print(eval_rews)
        if eval_rews > self.fitness[self.niche] and oniche_flag == False:
            self.fitness[self.niche] = eval_rews
            self.candidates[self.niche] = candidate
        self.niche += 1

        print(self.niche)
        
        self.fitness_eval.append(eval_rews)

        if self.niche == 0:
            self.cgen += 1

        # Pos-evaluate
        self.pos_evaluate()
        
        return (1000 - eval_rews)

    def pos_evaluate(self):
        self.avgfit = np.average(self.fitness_eval)  # compute the average fitness
        self.fitness_eval = []

        self.updateBest(
            self.bestestfit[0], self.bestestfit[1]
        )  # Stored if it is the best obtained so far

        # postevaluate best sample of the last generation
        # in openaiesp.py this is done the next generation, move this section before the section "evaluate samples" to produce identical results
        gfit = 0
        if self.bestsol is not None:
            self.policy.set_trainable_flat(self.bestsol)
            self.tnormepisodes += self.inormepisodes
            for t in range(self.policy.nttrials):
                if (
                    self.policy.normalize == 1
                    and self.normepisodes < self.tnormepisodes
                ):
                    self.policy.nn.normphase(1)
                    self.normepisodes += 1  # we collect normalization data
                    self.normalizationdatacollected = True
                else:
                    self.policy.nn.normphase(0)
                eval_rews, eval_length = self.policy.rollout(
                    1, seed=(self.seed + 100000 + t)
                )
                gfit += eval_rews
                self.steps += eval_length
            gfit /= self.policy.nttrials
            self.updateBestg(gfit, self.bestsol)
        print("BESTSOL", self.bestsol)

    def interniche(self): 
        self.colonized = [False for _ in range(self.number_niches**2)]
        fitMatrix = np.zeros(shape=(self.number_niches, self.number_niches))

        for niche in range(self.number_niches):
            for miche in range(self.number_niches):
                if miche != niche:
                    # Evaluate center of niche n in niche m
                    self.evaluate(self.candidates[niche], miche)
                    fitMatrix[niche][miche] = self.avgfit
                else:
                    fitMatrix[niche][miche] = -99999999
                    
        for miche in range(self.number_niches):
            # biche = best niche in miche
            biche = np.argmax(fitMatrix[:][miche])
            maxFit = fitMatrix[biche][miche]
            if maxFit > self.fitness[miche]:
                biche = np.argmax(fitMatrix[:][miche])
                print("Niche", biche+1, "colonized niche", miche+1)
                self.colonizer[miche] = biche

                for i in range(self.number_niches):
                    fitMatrix[i][biche] = -99999999
                    fitMatrix[miche][i] = -99999999

                # Replace i with o in niche m
                self.fitness[miche] = maxFit
                # Replace center of niche m with center of niche j
                self.candidates[miche] = self.candidates[biche]
        print('FUNCIONA')

    def run(self):

        self.setProcess()  # initialize class variables
        start_time = time.time()
        last_save_time = start_time
        elapsed = 0
        self.steps = 0
        self.cgen = 0
        print(
            "Salimans: seed %d maxmsteps %d  noiseStdDev %lf symseed %d nparams %d"
            % (
                self.seed,
                self.maxsteps / 1000000,
                self.noiseStdDev,
                self.symseed,
                self.nparams,
            )
        )
        self.bestestfit = (-99999999, None)
        self.fitness_eval = []

        random_niches = []
        num_random_niches = self.number_niches*100

        for _ in range(num_random_niches):
            random_niches.append([random.randint(1, num_random_niches*10) for _ in range(self.policy.ntrials)])

        self.niches = [0 for _ in range(self.number_niches)]
 
        for niche in range(self.number_niches): 
            self.niches[niche] = random_niches[niche]

        self.niche = 0

        while self.steps < self.maxsteps:

            self.cma_es.optimize(self.evaluate)
            
            self.result_pretty()
            
            # Interniche each 50 generations
            if self.cgen % 50 == 0:
               self.interniche()
            
            self.stat = np.append(
                self.stat,
                [
                    self.steps,
                    self.bestfit,
                    self.bestgfit,
                    self.bfit,
                    self.avgfit,
                    self.avecenter,
                ],
            )  # store performance across generations

            if (time.time() - last_save_time) > (self.saveeach * 60):
                self.savedata()  # save data on files
                last_save_time = time.time()

            if self.normalizationdatacollected:
                self.policy.nn.updateNormalizationVectors()  # update the normalization vectors with the new data collected
                self.normalizationdatacollected = False

            print(
                "Seed %d (%.1f%%) gen %d msteps %d bestfit %.2f bestgfit %.2f bestsam %.2f avg %.2f"
                % (
                    self.seed,
                    self.steps / float(self.maxsteps) * 100,
                    self.cgen,
                    self.steps / 1000000,
                    self.bestfit,
                    self.bestgfit,
                    self.bfit,
                    self.avgfit,
                )
            )

        self.savedata()  # save data at the end of evolution

        # print simulation time
        end_time = time.time()
        print("Simulation time: %dm%ds " % (divmod(end_time - start_time, 60)))
