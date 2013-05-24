# -*- coding: utf-8 -*-
from cidades_dic import cidades_dic
from repository.models import Contact

#tabela reposiroty_contact

def getEstadoDaCidade(cidade):
    '''funcao1 que recebe uma cidade e retorna o estado caso 
       encontre a cidade em dic_cidades caso contrario retorna 'NE'
    >>> getEstadoDaCidade('Rio de Janeiro')
    'RJ'
    >>> getEstadoDaCidade('lkslsj çlsfd')
    'NE'
    '''
    try:
        tupla_estado = cidades_dic[cidade]
        sigla_estado = tupla_estado[1]
    except:
        sigla_estado = 'NE'
    return sigla_estado 

def geraListaTuplasEstado():
    '''
     funcao2 que faz a query em reposiroty_contact retorna uma lista de 
     tuplas (id,cidade, estado) usando a funcao acima
    '''
    lista_tuplas = []
    all_contacts = Contact.objects.all()
    for contact in all_contacts:
        id_pk = contact.pk
        print id_pk
        cidade = contact.city
        estado = getEstadoDaCidade(contact.city)
        tupla_info = (id_pk, cidade, estado)
        lista_tuplas.append(tupla_info)
    return lista_tuplas

def updateEstadoFromTupla(tupla_info):
    '''
     funcao3 que recebe uma tupla (id, cidade, estado) e faz um 
     update na coluna state com o estado da tupla
    ''' 
    pkPar = tupla_info[0]
    estado = tupla_info[2]
    cidade = tupla_info[1]
    obj = Contact.objects.get(pk=pkPar)
    obj.state = estado
    obj.save()
    print "id:%s cidade:%s estado update:%s" % tupla_info

def main():
    '''
    funcao4 main que seta uma variavel com lista 
    gerada com funcao1 varre essa lista fazendo up
    dates com a funcao2
    '''
    lista_tuplas_estado = geraListaTuplasEstado()
    for tupla in lista_tuplas_estado:
        try:
            updateEstadoFromTupla(tupla)
        except:
            print "erro em de update tupla%s " % tupla

if __name__ == "__main__":
    import doctest
    doctest.testmod()
    #main()
