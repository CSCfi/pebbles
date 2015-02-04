app.controller('AccountController', ['$scope', 'AuthService', 'Restangular',
                             function($scope,   AuthService,   Restangular) {
    var user = Restangular.one('users', AuthService.getUserId());
    var key = null;
    var key_url = null;

    $scope.key_url = function() {
        return key_url;
    }

    $scope.key_downloadable = function() {
        if (key) {
            return true;
        }
        return false;
    };

    $scope.generate_key = function() {
        user.post('keypairs').then(function(response) {
            key = response.private_key;
            key_url = window.URL.createObjectURL(new Blob([key], {type: "application/octet-stream"}));
        });
    };
}]);
